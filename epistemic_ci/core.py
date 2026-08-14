from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence
import hashlib
import json
import os
import shutil
import subprocess
import tempfile


OBSERVATION_SCHEMA = "epistemic-ci.observation.v1"
BINDING_SCHEMA = "epistemic-ci.final-artifact-binding.v1"
RESULT_SCHEMA = "epistemic-ci.result.v1"
DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 3600
MAX_CAPTURE_CHARS = 8_000
DEFAULT_COPY_EXCLUDES = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    "dist",
    "build",
    "*.egg-info",
    "epistemic-ci-result.json",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    reason: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class CommandResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None


class ConfigurationError(ValueError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot load config: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigurationError("config root must be a JSON object")
    return data


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _trim(value: str) -> str:
    if len(value) <= MAX_CAPTURE_CHARS:
        return value
    return value[:MAX_CAPTURE_CHARS] + "\n...[truncated]"


def _command(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{field} must be a non-empty JSON array")
    if any(not isinstance(part, str) or not part for part in value):
        raise ConfigurationError(f"{field} entries must be non-empty strings")
    return list(value)


def _timeout(value: Any, field: str) -> int:
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{field} must be an integer")
    if not 1 <= value <= MAX_TIMEOUT_SECONDS:
        raise ConfigurationError(f"{field} must be between 1 and {MAX_TIMEOUT_SECONDS}")
    return value


def run_command(command: Sequence[str], cwd: Path, timeout_seconds: int) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            returncode=None,
            stdout=_trim(exc.stdout or ""),
            stderr=_trim(exc.stderr or ""),
            timed_out=True,
            error=f"command exceeded {timeout_seconds} seconds",
        )
    except OSError as exc:
        return CommandResult(None, "", "", error=str(exc))
    return CommandResult(
        completed.returncode,
        _trim(completed.stdout),
        _trim(completed.stderr),
    )


def _command_details(result: CommandResult) -> dict[str, Any]:
    details: dict[str, Any] = {"returncode": result.returncode}
    if result.timed_out:
        details["timed_out"] = True
    if result.error:
        details["error"] = result.error
    if result.stderr:
        details["stderr"] = result.stderr
    return details


def _copy_excludes(config: dict[str, Any]) -> tuple[str, ...]:
    extra = config.get("workspace_exclude", [])
    if not isinstance(extra, list) or any(not isinstance(item, str) or not item for item in extra):
        raise ConfigurationError("workspace_exclude must be an array of non-empty strings")
    return DEFAULT_COPY_EXCLUDES + tuple(extra)


@contextmanager
def isolated_workspace(root: Path, config: dict[str, Any]) -> Iterator[Path]:
    source = root.resolve(strict=True)
    if not source.is_dir():
        raise ConfigurationError("root must be a directory")
    with tempfile.TemporaryDirectory(prefix="epistemic-ci-") as directory:
        destination = Path(directory) / "workspace"
        shutil.copytree(
            source,
            destination,
            symlinks=True,
            ignore=shutil.ignore_patterns(*_copy_excludes(config)),
        )
        yield destination


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _safe_file(root: Path, relative: Any, field: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ConfigurationError(f"{field} must be a non-empty relative path")
    raw = Path(relative)
    if raw.is_absolute():
        raise ConfigurationError(f"{field} must stay inside the workspace")
    workspace = root.resolve(strict=True)
    candidate = (workspace / raw).resolve(strict=True)
    if not _inside(workspace, candidate):
        raise ConfigurationError(f"{field} escapes the workspace")
    if not candidate.is_file():
        raise ConfigurationError(f"{field} must name a regular file")
    return candidate


def _apply_text_mutation(root: Path, mutation: Any, field: str) -> str:
    if not isinstance(mutation, dict):
        raise ConfigurationError(f"{field} must be an object")
    name = mutation.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigurationError(f"{field}.name must be a non-empty string")
    target = _safe_file(root, mutation.get("path"), f"{field}.path")
    search = mutation.get("search")
    replace = mutation.get("replace")
    if not isinstance(search, str) or not search:
        raise ConfigurationError(f"{field}.search must be a non-empty string")
    if not isinstance(replace, str):
        raise ConfigurationError(f"{field}.replace must be a string")
    if search == replace:
        raise ConfigurationError(f"{field} does not change the target")
    try:
        original = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(f"{field}.path must be UTF-8 text") from exc
    occurrences = original.count(search)
    if occurrences != 1:
        raise ConfigurationError(
            f"{field}.search must match exactly once; found {occurrences} matches"
        )
    target.write_text(original.replace(search, replace, 1), encoding="utf-8")
    return name


def _section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name)
    if not isinstance(value, dict):
        raise ConfigurationError(f"{name} must be an object")
    return value


def check_vacuous_test(root: Path, config: dict[str, Any]) -> CheckResult:
    name = "vacuous-test"
    try:
        section = _section(config, "vacuous_test")
        verify = _command(section.get("verify_command"), "vacuous_test.verify_command")
        timeout = _timeout(section.get("timeout_seconds"), "vacuous_test.timeout_seconds")
        mutations = section.get("mutations")
        if not isinstance(mutations, list) or not mutations:
            raise ConfigurationError("vacuous_test.mutations must be a non-empty array")

        with isolated_workspace(root, config) as workspace:
            baseline = run_command(verify, workspace, timeout)
        if baseline.returncode != 0:
            return CheckResult(
                name,
                "fail",
                "baseline verification does not pass in an isolated workspace",
                _command_details(baseline),
            )

        killed: list[str] = []
        survivors: list[str] = []
        invalid: list[str] = []
        for index, mutation in enumerate(mutations):
            try:
                with isolated_workspace(root, config) as workspace:
                    mutation_name = _apply_text_mutation(
                        workspace, mutation, f"vacuous_test.mutations[{index}]"
                    )
                    result = run_command(verify, workspace, timeout)
                if result.returncode == 0:
                    survivors.append(mutation_name)
                else:
                    killed.append(mutation_name)
            except (ConfigurationError, OSError) as exc:
                invalid.append(str(exc))

        details = {
            "killed": killed,
            "survivors": survivors,
            "invalid": invalid,
            "total": len(mutations),
        }
        if survivors or invalid or len(killed) != len(mutations):
            return CheckResult(
                name,
                "fail",
                "every declared source/input mutation must make verification fail",
                details,
            )
        return CheckResult(
            name,
            "pass",
            "every declared source/input mutation made verification fail",
            details,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def _generated_files(root: Path, values: Any, field: str) -> list[Path]:
    if not isinstance(values, list) or not values:
        raise ConfigurationError(f"{field} must be a non-empty array")
    workspace = root.resolve(strict=True)
    found: dict[str, Path] = {}
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            raise ConfigurationError(f"{field}[{index}] must be a non-empty relative path")
        raw = Path(value)
        if raw.is_absolute():
            raise ConfigurationError(f"{field}[{index}] must stay inside the workspace")
        candidate = (workspace / raw).resolve(strict=True)
        if not _inside(workspace, candidate):
            raise ConfigurationError(f"{field}[{index}] escapes the workspace")
        if candidate.is_file():
            candidates = [candidate]
        elif candidate.is_dir():
            candidates = sorted(path.resolve(strict=True) for path in candidate.rglob("*") if path.is_file())
        else:
            candidates = []
        for path in candidates:
            if not _inside(workspace, path):
                raise ConfigurationError(f"{field}[{index}] contains a file outside the workspace")
            found[str(path.relative_to(workspace))] = path
    if not found:
        raise ConfigurationError(f"{field} matched no generated files after preparation")
    return [found[key] for key in sorted(found)]


def _manifest_fingerprint(root: Path, files: Sequence[Path]) -> str:
    workspace = root.resolve(strict=True)
    digest = hashlib.sha256()
    for path in files:
        relative = str(path.resolve(strict=True).relative_to(workspace)).encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def check_executable_pass_condition(root: Path, config: dict[str, Any]) -> CheckResult:
    name = "executable-pass-condition"
    try:
        section = _section(config, "executable_pass_condition")
        prepare = _command(
            section.get("prepare_command"), "executable_pass_condition.prepare_command"
        )
        check = _command(
            section.get("check_command"), "executable_pass_condition.check_command"
        )
        timeout = _timeout(
            section.get("timeout_seconds"), "executable_pass_condition.timeout_seconds"
        )
        generated_paths = section.get("generated_paths")
        mutations = section.get("mutations")
        if not isinstance(mutations, list) or not mutations:
            raise ConfigurationError(
                "executable_pass_condition.mutations must be a non-empty array"
            )

        with isolated_workspace(root, config) as workspace:
            prepared = run_command(prepare, workspace, timeout)
            if prepared.returncode != 0:
                return CheckResult(
                    name,
                    "fail",
                    "generated-output preparation failed",
                    _command_details(prepared),
                )
            files = _generated_files(
                workspace,
                generated_paths,
                "executable_pass_condition.generated_paths",
            )
            baseline_fingerprint = _manifest_fingerprint(workspace, files)
            baseline = run_command(check, workspace, timeout)
        if baseline.returncode != 0:
            return CheckResult(
                name,
                "fail",
                "pass-condition check fails against freshly generated output",
                _command_details(baseline),
            )

        killed: list[str] = []
        survivors: list[str] = []
        invalid: list[str] = []
        for index, mutation in enumerate(mutations):
            try:
                with isolated_workspace(root, config) as workspace:
                    prepared = run_command(prepare, workspace, timeout)
                    if prepared.returncode != 0:
                        raise ConfigurationError(
                            f"preparation failed for output mutation {index}"
                        )
                    files = _generated_files(
                        workspace,
                        generated_paths,
                        "executable_pass_condition.generated_paths",
                    )
                    allowed = {path.resolve(strict=True) for path in files}
                    target = _safe_file(
                        workspace,
                        mutation.get("path") if isinstance(mutation, dict) else None,
                        f"executable_pass_condition.mutations[{index}].path",
                    )
                    if target.resolve(strict=True) not in allowed:
                        raise ConfigurationError(
                            f"executable_pass_condition.mutations[{index}].path is not a declared generated file"
                        )
                    mutation_name = _apply_text_mutation(
                        workspace,
                        mutation,
                        f"executable_pass_condition.mutations[{index}]",
                    )
                    result = run_command(check, workspace, timeout)
                if result.returncode == 0:
                    survivors.append(mutation_name)
                else:
                    killed.append(mutation_name)
            except (ConfigurationError, OSError) as exc:
                invalid.append(str(exc))

        details = {
            "generated_file_count": len(files),
            "generated_fingerprint": baseline_fingerprint,
            "killed": killed,
            "survivors": survivors,
            "invalid": invalid,
            "total": len(mutations),
        }
        if survivors or invalid or len(killed) != len(mutations):
            return CheckResult(
                name,
                "fail",
                "the declared pass condition must reject every planted generated-output defect",
                details,
            )
        return CheckResult(
            name,
            "pass",
            "the pass condition accepted fresh output and rejected every planted output defect",
            details,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ConfigurationError(f"{field} must be a sha256 digest")
    prefix = "sha256:"
    if not value.startswith(prefix):
        raise ConfigurationError(f"{field} must use the sha256:<64 lowercase hex> form")
    hexdigest = value[len(prefix) :]
    if len(hexdigest) != 64 or any(character not in "0123456789abcdef" for character in hexdigest):
        raise ConfigurationError(f"{field} must use the sha256:<64 lowercase hex> form")
    return value


def _observation(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("observation command must emit one JSON object") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("observation command must emit one JSON object")
    if value.get("schema") != OBSERVATION_SCHEMA:
        raise ConfigurationError(f"observation schema must be {OBSERVATION_SCHEMA}")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 256:
        raise ConfigurationError("observation.run_id must be a string of 1-256 characters")
    population = value.get("population")
    result = value.get("result")
    if not isinstance(population, dict) or not isinstance(result, dict):
        raise ConfigurationError("observation must contain population and result objects")
    count = population.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ConfigurationError("observation.population.count must be a positive integer")
    normalized = {
        "schema": OBSERVATION_SCHEMA,
        "run_id": run_id,
        "population": {
            "count": count,
            "fingerprint": _digest(
                population.get("fingerprint"), "observation.population.fingerprint"
            ),
        },
        "result": {
            "fingerprint": _digest(
                result.get("fingerprint"), "observation.result.fingerprint"
            )
        },
    }
    normalized["observation_fingerprint"] = _canonical_sha256(normalized)
    return normalized


def check_observation_surface(root: Path, config: dict[str, Any]) -> CheckResult:
    name = "observation-surface"
    try:
        section = _section(config, "observation_surface")
        command = _command(section.get("command"), "observation_surface.command")
        timeout = _timeout(
            section.get("timeout_seconds"), "observation_surface.timeout_seconds"
        )
        with isolated_workspace(root, config) as workspace:
            result = run_command(command, workspace, timeout)
        if result.returncode != 0:
            return CheckResult(
                name,
                "fail",
                "observation command failed",
                _command_details(result),
            )
        observation = _observation(result.stdout)
        return CheckResult(
            name,
            "pass",
            "one structured observation binds the checked population and result fingerprints",
            observation,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def _artifact_manifest(root: Path, files: Sequence[Path]) -> list[dict[str, str]]:
    workspace = root.resolve(strict=True)
    return [
        {
            "path": path.resolve(strict=True).relative_to(workspace).as_posix(),
            "sha256": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
        }
        for path in files
    ]


def _binding_receipt(
    root: Path,
    receipt_path: Path,
    files: Sequence[Path],
) -> dict[str, Any]:
    try:
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError("binding receipt must contain one UTF-8 JSON object") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("binding receipt must contain one JSON object")
    if value.get("schema") != BINDING_SCHEMA:
        raise ConfigurationError(f"binding receipt schema must be {BINDING_SCHEMA}")
    run_id = value.get("run_id")
    if not isinstance(run_id, str) or not 1 <= len(run_id) <= 256:
        raise ConfigurationError("binding receipt run_id must be a string of 1-256 characters")
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ConfigurationError("binding receipt artifacts must be a non-empty array")

    normalized_artifacts: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise ConfigurationError(f"binding receipt artifacts[{index}] must be an object")
        path = artifact.get("path")
        if not isinstance(path, str) or not path:
            raise ConfigurationError(
                f"binding receipt artifacts[{index}].path must be a non-empty string"
            )
        if path in seen:
            raise ConfigurationError(f"binding receipt contains duplicate artifact path: {path}")
        seen.add(path)
        normalized_artifacts.append(
            {
                "path": path,
                "sha256": _digest(
                    artifact.get("sha256"),
                    f"binding receipt artifacts[{index}].sha256",
                ),
            }
        )

    expected = _artifact_manifest(root, files)
    if normalized_artifacts != expected:
        raise ConfigurationError(
            "binding receipt must exactly match every declared final artifact in path order"
        )
    normalized: dict[str, Any] = {
        "schema": BINDING_SCHEMA,
        "run_id": run_id,
        "artifacts": normalized_artifacts,
    }
    normalized["receipt_fingerprint"] = _canonical_sha256(normalized)
    return normalized


def _prepare_binding_workspace(
    workspace: Path,
    section: dict[str, Any],
    prepare: Sequence[str],
    timeout: int,
) -> tuple[list[Path], Path, dict[str, Any]]:
    prepared = run_command(prepare, workspace, timeout)
    if prepared.returncode != 0:
        raise ConfigurationError("final-artifact preparation failed")
    files = _generated_files(
        workspace,
        section.get("artifact_paths"),
        "final_artifact_binding.artifact_paths",
    )
    receipt_path = _safe_file(
        workspace,
        section.get("receipt_path"),
        "final_artifact_binding.receipt_path",
    )
    if receipt_path.resolve(strict=True) in {path.resolve(strict=True) for path in files}:
        raise ConfigurationError(
            "final_artifact_binding.receipt_path must remain outside artifact_paths"
        )
    receipt = _binding_receipt(workspace, receipt_path, files)
    return files, receipt_path, receipt


def _tamper_receipt(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    current = value["artifacts"][0]["sha256"]
    replacement = "sha256:" + ("0" * 64)
    if current == replacement:
        replacement = "sha256:" + ("1" * 64)
    value["artifacts"][0]["sha256"] = replacement
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def check_final_artifact_binding(root: Path, config: dict[str, Any]) -> CheckResult:
    name = "final-artifact-binding"
    try:
        section = _section(config, "final_artifact_binding")
        prepare = _command(
            section.get("prepare_command"),
            "final_artifact_binding.prepare_command",
        )
        verify = _command(
            section.get("verify_command"),
            "final_artifact_binding.verify_command",
        )
        timeout = _timeout(
            section.get("timeout_seconds"),
            "final_artifact_binding.timeout_seconds",
        )

        with isolated_workspace(root, config) as workspace:
            files, receipt_path, receipt = _prepare_binding_workspace(
                workspace, section, prepare, timeout
            )
            baseline = run_command(verify, workspace, timeout)
            receipt_after_verification = _binding_receipt(workspace, receipt_path, files)
            if receipt_after_verification != receipt:
                raise ConfigurationError(
                    "binding verifier changed the final artifacts or receipt during verification"
                )
            manifest_fingerprint = _canonical_sha256(_artifact_manifest(workspace, files))
            artifact_names = [
                path.resolve(strict=True).relative_to(workspace.resolve(strict=True)).as_posix()
                for path in files
            ]
        if baseline.returncode != 0:
            return CheckResult(
                name,
                "fail",
                "binding verifier rejects the freshly produced receipt and artifacts",
                _command_details(baseline),
            )

        killed: list[str] = []
        survivors: list[str] = []
        invalid: list[str] = []
        for artifact_name in artifact_names:
            mutation_name = f"alter-artifact:{artifact_name}"
            try:
                with isolated_workspace(root, config) as workspace:
                    files, _receipt_path, _receipt = _prepare_binding_workspace(
                        workspace, section, prepare, timeout
                    )
                    targets = {
                        path.resolve(strict=True)
                        .relative_to(workspace.resolve(strict=True))
                        .as_posix(): path
                        for path in files
                    }
                    target = targets[artifact_name]
                    target.write_bytes(target.read_bytes() + b"\nepistemic-ci:altered\n")
                    try:
                        _binding_receipt(workspace, _receipt_path, files)
                    except ConfigurationError:
                        pass
                    else:
                        raise ConfigurationError(
                            "internal binding validation accepted altered artifact: "
                            f"{artifact_name}"
                        )
                    result = run_command(verify, workspace, timeout)
                if result.returncode == 0:
                    survivors.append(mutation_name)
                else:
                    killed.append(mutation_name)
            except (ConfigurationError, KeyError, OSError) as exc:
                invalid.append(str(exc))

        receipt_mutation = "tamper-receipt-digest"
        try:
            with isolated_workspace(root, config) as workspace:
                files, receipt_path, _receipt = _prepare_binding_workspace(
                    workspace, section, prepare, timeout
                )
                _tamper_receipt(receipt_path)
                try:
                    _binding_receipt(workspace, receipt_path, files)
                except ConfigurationError:
                    pass
                else:
                    raise ConfigurationError(
                        "internal binding validation accepted a tampered receipt"
                    )
                result = run_command(verify, workspace, timeout)
            if result.returncode == 0:
                survivors.append(receipt_mutation)
            else:
                killed.append(receipt_mutation)
        except (ConfigurationError, KeyError, OSError) as exc:
            invalid.append(str(exc))

        total = len(artifact_names) + 1
        details = {
            "artifact_count": len(artifact_names),
            "artifacts": artifact_names,
            "manifest_fingerprint": manifest_fingerprint,
            "receipt_fingerprint": receipt["receipt_fingerprint"],
            "killed": killed,
            "survivors": survivors,
            "invalid": invalid,
            "total": total,
        }
        if survivors or invalid or len(killed) != total:
            return CheckResult(
                name,
                "fail",
                "the binding verifier must reject every altered artifact and tampered receipt",
                details,
            )
        return CheckResult(
            name,
            "pass",
            "the receipt exactly binds the final artifacts and the verifier "
            "rejected every substitution",
            details,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def _declared_mutation_paths(config: dict[str, Any], section_name: str) -> set[str]:
    section = config.get(section_name)
    if not isinstance(section, dict):
        return set()
    mutations = section.get("mutations")
    if not isinstance(mutations, list):
        return set()
    paths: set[str] = set()
    for mutation in mutations:
        if isinstance(mutation, dict) and isinstance(mutation.get("path"), str):
            paths.add(Path(mutation["path"]).as_posix())
    return paths


def check_pinned_input_binding(root: Path, config: dict[str, Any]) -> CheckResult:
    """A declared-pinned input must be read from its pin, not from the workspace.

    THE OTHER FOUR CHECKS ALL HAVE ONE POLARITY: mutate something, verification
    must fail. They establish that checking is SENSITIVE to corruption. This one
    is the other half, and it exists because sensitivity in the wrong place is
    itself a defect.

    A runner that pins an input claims its results came from specific bytes. If
    it actually reads the working-tree copy, that claim is true only while nobody
    edits the file -- true by coincidence rather than construction. The failure
    is silent: every recorded digest still matches, because the digest is taken
    of the same working-tree copy that was executed.

    HOW THIS RECONCILES WITH vacuous-test RATHER THAN CONTRADICTING IT. The two
    checks partition the inputs:

        live   read from the workspace at run time.  vacuous-test is correct:
               corrupt it and verification must fail.
        pinned read from an immutable reference.     this check is correct:
               corrupt the workspace copy and the RESULT MUST NOT MOVE, because
               the run never reads it.

    An input cannot be both. A path declared as a vacuous-test mutation target
    AND as a pin is a contradiction in the configuration, and is rejected rather
    than resolved -- because either answer would be wrong for one of the two
    checks, and guessing which is the thing this tool exists to stop.

    WHAT A PASS ESTABLISHES, AND WHAT IT DOES NOT. Insensitivity is checked
    generically and always. Sensitivity -- that corrupting what the pin RESOLVES
    TO makes the run fail -- depends on the pin mechanism, which this tool cannot
    know. A pin may be a commit, a digest, an archive or a registry reference.
    Where the configuration supplies `tamper_command`, sensitivity is checked and
    must fail the run. Where it does not, sensitivity is reported as NOT
    ESTABLISHED for that pin rather than assumed, and the count is carried into
    the assurance bound.
    """
    name = "pinned-input-binding"
    try:
        if "pinned_input_binding" not in config:
            # Not every project pins an input, and a missing section must not
            # break the four checks that predate this one. But "pass" with
            # nothing checked is the vacuous result this tool exists to prevent,
            # so it is stated in the reason and counted in the assurance bound,
            # where a summariser cannot drop it silently.
            return CheckResult(
                name,
                "pass",
                "no pinned inputs declared; this check establishes nothing here",
                {"declared_pins": 0, "vacuous": True},
            )
        section = _section(config, "pinned_input_binding")
        run = _command(section.get("run_command"), "pinned_input_binding.run_command")
        timeout = _timeout(
            section.get("timeout_seconds"), "pinned_input_binding.timeout_seconds"
        )
        result_paths = section.get("result_paths")
        pins = section.get("pins")
        if not isinstance(pins, list) or not pins:
            raise ConfigurationError("pinned_input_binding.pins must be a non-empty array")

        declared_live = _declared_mutation_paths(config, "vacuous_test")
        for index, pin in enumerate(pins):
            if not isinstance(pin, dict) or not isinstance(pin.get("path"), str):
                raise ConfigurationError(
                    f"pinned_input_binding.pins[{index}].path must be a non-empty relative path"
                )
            posix = Path(pin["path"]).as_posix()
            if posix in declared_live:
                raise ConfigurationError(
                    f"pinned_input_binding.pins[{index}].path {posix!r} is also a "
                    "vacuous_test mutation target. An input is read either from the "
                    "workspace or from a pin, never both, and the two checks require "
                    "opposite behaviour of it."
                )

        with isolated_workspace(root, config) as workspace:
            baseline = run_command(run, workspace, timeout)
            if baseline.returncode != 0:
                return CheckResult(
                    name,
                    "fail",
                    "baseline run does not succeed in an isolated workspace",
                    _command_details(baseline),
                )
            files = _generated_files(workspace, result_paths, "pinned_input_binding.result_paths")
            baseline_fingerprint = _manifest_fingerprint(workspace, files)

        held: list[str] = []
        moved: list[str] = []
        invalid: list[str] = []
        sensitivity_established: list[str] = []
        sensitivity_unestablished: list[str] = []

        for index, pin in enumerate(pins):
            field = f"pinned_input_binding.pins[{index}]"
            try:
                with isolated_workspace(root, config) as workspace:
                    pin_name = _apply_text_mutation(workspace, pin, field)
                    result = run_command(run, workspace, timeout)
                    if result.returncode != 0:
                        moved.append(f"{pin_name}: run failed after workspace edit")
                        continue
                    files = _generated_files(
                        workspace, result_paths, "pinned_input_binding.result_paths"
                    )
                    if _manifest_fingerprint(workspace, files) != baseline_fingerprint:
                        moved.append(f"{pin_name}: result changed, so the input is live, not pinned")
                        continue
                    held.append(pin_name)

                tamper = pin.get("tamper_command")
                if tamper is None:
                    sensitivity_unestablished.append(pin_name)
                    continue
                tamper_command = _command(tamper, f"{field}.tamper_command")
                with isolated_workspace(root, config) as workspace:
                    tampered = run_command(tamper_command, workspace, timeout)
                    if tampered.returncode != 0:
                        invalid.append(f"{field}.tamper_command failed to run")
                        continue
                    after = run_command(run, workspace, timeout)
                    if after.returncode == 0:
                        moved.append(
                            f"{pin_name}: run still succeeded after the pin was repointed"
                        )
                    else:
                        sensitivity_established.append(pin_name)
            except (ConfigurationError, OSError) as exc:
                invalid.append(str(exc))

        details = {
            "held": held,
            "moved": moved,
            "invalid": invalid,
            "sensitivity_established": sensitivity_established,
            "sensitivity_not_established": sensitivity_unestablished,
            "total": len(pins),
            "baseline_fingerprint": baseline_fingerprint,
        }
        if moved or invalid or len(held) != len(pins):
            return CheckResult(
                name,
                "fail",
                "every declared pinned input must leave the result unchanged when its "
                "workspace copy is corrupted",
                details,
            )
        return CheckResult(
            name,
            "pass",
            "every declared pinned input was read from its pin, not from the workspace",
            details,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def _outcome_matrix(
    root: Path,
    config: dict[str, Any],
    tests: list[dict[str, Any]],
    mutations: list[Any],
    timeout: int,
    field: str,
) -> tuple[dict[str, list[bool]], list[str], list[str]]:
    """Run every declared test against the clean tree and each mutation.

    Returns {test name: [clean, mut0, mut1, ...]} where True means the test
    FAILED (fired). Shared by checks 6 and 7 because both are questions about
    the SHAPE of this matrix rather than about any single cell -- one asks
    whether a row varies at all, the other whether two rows are identical.
    """
    names: list[str] = []
    commands: list[Sequence[str]] = []
    for index, test in enumerate(tests):
        if not isinstance(test, dict):
            raise ConfigurationError(f"{field}.tests[{index}] must be an object")
        name = test.get("name")
        if not isinstance(name, str) or not name:
            raise ConfigurationError(f"{field}.tests[{index}].name must be a non-empty string")
        names.append(name)
        commands.append(_command(test.get("command"), f"{field}.tests[{index}].command"))

    matrix: dict[str, list[bool]] = {name: [] for name in names}
    columns = ["clean"]
    invalid: list[str] = []

    with isolated_workspace(root, config) as workspace:
        for name, command in zip(names, commands):
            matrix[name].append(run_command(command, workspace, timeout).returncode != 0)

    for index, mutation in enumerate(mutations):
        try:
            with isolated_workspace(root, config) as workspace:
                columns.append(_apply_text_mutation(workspace, mutation, f"{field}.mutations[{index}]"))
                for name, command in zip(names, commands):
                    matrix[name].append(run_command(command, workspace, timeout).returncode != 0)
        except (ConfigurationError, OSError) as exc:
            invalid.append(str(exc))
            for name in names:
                matrix[name].append(False)
            columns.append(f"invalid[{index}]")
    return matrix, columns, invalid


def check_control_discrimination(root: Path, config: dict[str, Any]) -> CheckResult:
    """A control that fires on every input measures the population, not the checker.

    Vacuous Test asks *does a defect cause failure?*. It never asks *does the
    ABSENCE of a defect cause anything different?*. A control declared
    must-be-non-zero that fires on every eligible input passes Vacuous Test
    while carrying no discriminating power at all.

    The worked instance in issue #3 is the sharp kind: a registered control
    required that side-inconsistent worlds where two sets differ must exist,
    and it fired 44,450/44,450 exhaustively and 52,178/52,178 randomized --
    not "most", all, and provably so, because the property is entailed by the
    definition. Any implementation that computes the two sets at all passes it.
    It was filed under checker power and it measured the population.

    This check requires each declared test to fire on at least one input and
    NOT fire on at least one input, across the clean tree and the declared
    mutations. A row of all-True is a control that cannot discriminate; a row
    of all-False is a test that never fires at all.
    """
    name = "control-discrimination"
    try:
        if "control_discrimination" not in config:
            return CheckResult(
                name, "pass",
                "no controls declared; this check establishes nothing here",
                {"declared_tests": 0, "vacuous": True},
            )
        section = _section(config, "control_discrimination")
        timeout = _timeout(
            section.get("timeout_seconds"), "control_discrimination.timeout_seconds"
        )
        tests = section.get("tests")
        mutations = section.get("mutations")
        if not isinstance(tests, list) or not tests:
            raise ConfigurationError("control_discrimination.tests must be a non-empty array")
        if not isinstance(mutations, list) or not mutations:
            raise ConfigurationError("control_discrimination.mutations must be a non-empty array")

        matrix, columns, invalid = _outcome_matrix(
            root, config, tests, mutations, timeout, "control_discrimination"
        )

        always: list[str] = []
        never: list[str] = []
        discriminating: list[str] = []
        for test_name, row in matrix.items():
            if all(row):
                always.append(test_name)
            elif not any(row):
                never.append(test_name)
            else:
                discriminating.append(test_name)

        details = {
            "columns": columns,
            "matrix": {k: list(v) for k, v in matrix.items()},
            "discriminating": discriminating,
            "fires_on_everything": always,
            "never_fires": never,
            "invalid": invalid,
        }
        if always or never or invalid:
            return CheckResult(
                name, "fail",
                "every declared control must fire on at least one input and not fire "
                "on at least one; a control that fires on everything measures the "
                "population, not the checker",
                details,
            )
        return CheckResult(
            name, "pass",
            "every declared control both fired and did not fire across the declared inputs",
            details,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def check_evidential_independence(root: Path, config: dict[str, Any]) -> CheckResult:
    """Two tests cited as separate evidence must not behave identically.

    Where one test is a logical corollary of another, both pass Vacuous Test --
    planting a defect makes both fail -- while only one carries independent
    evidence. The redundant green then gets counted twice.

    Implication is invisible to plant-a-defect checks precisely because the
    implied test DOES fail when the implying one fails. That correlation is the
    defect and it reads as health.

    Deciding implication in general is undecidable, so this does not attempt it.
    It reports the computable proxy: two declared tests whose fire pattern is
    IDENTICAL across the clean tree and every declared mutation are not
    distinguished by any evidence in this configuration. That is not proof of
    implication -- two genuinely independent tests can coincide on a small
    mutation set -- and the result says so rather than asserting redundancy.
    The remedy is a mutation that separates them, or an admission that they are
    one piece of evidence.
    """
    name = "evidential-independence"
    try:
        if "evidential_independence" not in config:
            return CheckResult(
                name, "pass",
                "no independent-evidence claims declared; this check establishes nothing here",
                {"declared_tests": 0, "vacuous": True},
            )
        section = _section(config, "evidential_independence")
        timeout = _timeout(
            section.get("timeout_seconds"), "evidential_independence.timeout_seconds"
        )
        tests = section.get("tests")
        mutations = section.get("mutations")
        if not isinstance(tests, list) or len(tests) < 2:
            raise ConfigurationError(
                "evidential_independence.tests must declare at least two tests; "
                "independence is a relation and needs a pair"
            )
        if not isinstance(mutations, list) or not mutations:
            raise ConfigurationError("evidential_independence.mutations must be a non-empty array")

        matrix, columns, invalid = _outcome_matrix(
            root, config, tests, mutations, timeout, "evidential_independence"
        )

        names = list(matrix)
        indistinguishable: list[list[str]] = []
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                if matrix[left] == matrix[right]:
                    indistinguishable.append([left, right])

        details = {
            "columns": columns,
            "matrix": {k: list(v) for k, v in matrix.items()},
            "indistinguishable_pairs": indistinguishable,
            "invalid": invalid,
            "note": (
                "identical fire patterns do not prove one test implies the other. "
                "They establish that no declared mutation separates them, so this "
                "configuration provides no evidence that they are independent."
            ),
        }
        if indistinguishable or invalid:
            return CheckResult(
                name, "fail",
                "tests cited as separate evidence must be separated by at least one "
                "declared mutation; identical fire patterns mean this configuration "
                "cannot tell them apart",
                details,
            )
        return CheckResult(
            name, "pass",
            "every pair of declared tests was separated by at least one mutation",
            details,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def check_effect_reachability(root: Path, config: dict[str, Any]) -> CheckResult:
    """The population must contain instances of the phenomenon the endpoint is about.

    All other checks interrogate the verification path. This one interrogates
    the POPULATION, and it is the only failure here that no amount of checking
    the checker can find: planting a defect does make verification fail, and the
    verifier is sound. The defect is that the corpus has no instances of the
    thing the endpoint measures, so the endpoint cannot move whatever the
    mechanism does.

    Issue #2's instance: 60 repositories, 71 planted defects, digest-manifested,
    bound to a run id, all checks green. The mechanism under test refuses a
    "clean" verdict when a search is INCOMPLETE. The corpus generator wrote only
    readable files:

        searched 208 · not_searched 0 · unavailable 0

    Incomplete coverage never occurred. The mechanism's only lever was never
    pulled, both arms produced identical results, and the registration was
    authored, authorised, pinned and run before anyone noticed the population
    was structurally incapable of answering the question.

    STRATA, NOT A SINGLE COUNT. The issue proposes a population predicate that
    must return more than zero. That catches the empty case but not the worked
    instance's real shape, which is a population where the condition is present
    in only ONE of its states -- 208 searched and 0 not-searched is a positive
    count and still cannot move the endpoint. So each declared stratum is
    required to be non-empty: if the result depends on a distinction, the corpus
    must contain instances on both sides of it.

    BOUNDED BY DECLARATION, like checks 1 and 2. The strata are the ones the
    configuration names. A population whose author declared only the strata it
    happens to contain will pass. That limit cannot be closed from inside this
    tool, because deciding which distinctions matter requires knowing what the
    claim is about -- which is the thing under study. It is reported instead.
    """
    name = "effect-reachability"
    try:
        if "effect_reachability" not in config:
            return CheckResult(
                name, "pass",
                "no endpoint strata declared; this check establishes nothing here",
                {"declared_strata": 0, "vacuous": True},
            )
        section = _section(config, "effect_reachability")
        endpoint = section.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            raise ConfigurationError("effect_reachability.endpoint must be a non-empty string")
        timeout = _timeout(
            section.get("timeout_seconds"), "effect_reachability.timeout_seconds"
        )
        strata = section.get("strata")
        if not isinstance(strata, list) or not strata:
            raise ConfigurationError(
                "effect_reachability.strata must be a non-empty array. If the endpoint "
                "depends on a distinction, name each side of it: a population with "
                "instances on only one side cannot move the endpoint."
            )

        counts: dict[str, int] = {}
        empty: list[str] = []
        invalid: list[str] = []
        with isolated_workspace(root, config) as workspace:
            for index, stratum in enumerate(strata):
                field = f"effect_reachability.strata[{index}]"
                if not isinstance(stratum, dict):
                    invalid.append(f"{field} must be an object")
                    continue
                label = stratum.get("name")
                if not isinstance(label, str) or not label:
                    invalid.append(f"{field}.name must be a non-empty string")
                    continue
                command = _command(stratum.get("count_command"), f"{field}.count_command")
                minimum = stratum.get("minimum_instances", 1)
                if not isinstance(minimum, int) or minimum < 1:
                    invalid.append(f"{field}.minimum_instances must be an integer >= 1")
                    continue
                result = run_command(command, workspace, timeout)
                if result.returncode != 0:
                    invalid.append(f"{field}.count_command failed to run")
                    continue
                text = (result.stdout or "").strip().splitlines()
                try:
                    value = int(text[-1].strip()) if text else -1
                except ValueError:
                    invalid.append(f"{field}.count_command must print an integer count")
                    continue
                counts[label] = value
                if value < minimum:
                    empty.append(f"{label}={value} (needs >= {minimum})")

        details = {
            "endpoint": endpoint,
            "counts": counts,
            "understocked_strata": empty,
            "invalid": invalid,
            "bounded_by": (
                "the strata this configuration names. A population whose author "
                "declared only the strata it happens to contain will pass."
            ),
        }
        if empty or invalid:
            return CheckResult(
                name, "fail",
                f"the population cannot exhibit the effect {endpoint!r} measures: "
                "every declared stratum must contain instances, or the endpoint "
                "cannot move whatever the mechanism does",
                details,
            )
        return CheckResult(
            name, "pass",
            f"the population contains instances in every stratum {endpoint!r} depends on",
            details,
        )
    except (ConfigurationError, OSError) as exc:
        return CheckResult(name, "fail", str(exc))


def run_all(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    if config.get("version") != 1:
        checks = [
            CheckResult(
                "configuration",
                "fail",
                "config version must be the integer 1",
            )
        ]
    else:
        checks = [
            check_vacuous_test(root, config),
            check_executable_pass_condition(root, config),
            check_observation_surface(root, config),
            check_final_artifact_binding(root, config),
            check_pinned_input_binding(root, config),
            check_control_discrimination(root, config),
            check_evidential_independence(root, config),
            check_effect_reachability(root, config),
        ]
    return {
        "schema": RESULT_SCHEMA,
        "status": "pass" if all(check.status == "pass" for check in checks) else "fail",
        "config_fingerprint": _canonical_sha256(config),
        "assurance_bound": _assurance_bound(config),
        "checks": [asdict(check) for check in checks],
    }


def _assurance_bound(config: dict[str, Any]) -> dict[str, Any]:
    """State what a passing result does and does not establish, in the result.

    Each check's own `reason` already says "every DECLARED mutation", which is
    accurate. The top-level `status: pass` carries no such qualifier, and it is
    the field a badge, a dashboard or a summary reads. A reader who sees only
    `pass` has no way to learn that the guarantee is bounded by a mutation set the
    configuration author chose.

    That bound is not a defect to be fixed by a stricter check. Whether a declared
    mutation set is representative cannot be decided without knowing which defects
    matter, which is the thing under study. An empty set and a no-op mutation are
    already rejected -- the former by explicit validation, the latter because an
    unchanged workspace leaves verification passing and the check then fails. What
    remains is a verifier whose author declared only defects it happens to catch,
    and no amount of checking inside this tool can distinguish that from a sound
    verifier.

    So the bound is reported rather than enforced, and reported in machine-readable
    form so that summarising the result cannot silently drop it.
    """
    counts: dict[str, int] = {}
    for section in ("vacuous_test", "executable_pass_condition"):
        value = config.get(section)
        if isinstance(value, dict) and isinstance(value.get("mutations"), list):
            counts[section] = len(value["mutations"])
    total = sum(counts.values())
    # Pins are NOT mutations and are counted separately. Folding them into the
    # mutation total would inflate the number a reader uses to judge how much a
    # pass established, in a tool whose whole purpose is to stop exactly that.
    pinned_section = config.get("pinned_input_binding")
    pins = (
        [pin for pin in pinned_section["pins"] if isinstance(pin, dict)]
        if isinstance(pinned_section, dict) and isinstance(pinned_section.get("pins"), list)
        else []
    )
    pinned_inputs = {
        "declared": len(pins),
        "with_sensitivity_check": sum(
            1 for pin in pins if pin.get("tamper_command") is not None
        ),
    }
    return {
        "declared_mutations": counts,
        "declared_mutations_total": total,
        "pinned_inputs": pinned_inputs,
        "establishes": (
            f"the configured verification path rejected each of the {total} "
            f"defect(s) declared in this configuration"
        ),
        "does_not_establish": (
            "that the verification path detects any defect that was not declared. "
            "The declared set is chosen by the configuration author and this tool "
            "cannot determine whether it is representative of the defects that "
            "matter."
        ),
    }
