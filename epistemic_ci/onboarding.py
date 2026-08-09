from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .core import ConfigurationError, load_config, run_all

ONBOARDING_SCHEMA = "epistemic-ci.onboarding.v1"
ANSWERS_SCHEMA = "epistemic-ci.onboarding-answers.v1"

_PRUNED_DIRECTORIES = {
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
}
_ARTIFACT_SUFFIXES = {".csv", ".html", ".json", ".pdf", ".sarif", ".xml"}
_ARTIFACT_TERMS = (
    "artifact",
    "coverage",
    "evidence",
    "finding",
    "report",
    "result",
    "summary",
)
_VERIFY_TERMS = (
    "cargo test",
    "go test",
    "npm test",
    "npm run test",
    "pytest",
    "unittest",
    "verify",
)


class OnboardingError(ValueError):
    pass


def _canonical_fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _iter_files(root: Path) -> Iterator[Path]:
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name not in _PRUNED_DIRECTORIES)
        for name in sorted(files):
            yield Path(directory) / name


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _add_command(
    commands: list[dict[str, str]],
    seen: set[str],
    command: str,
    source: str,
) -> None:
    normalized = " ".join(command.split())
    if not normalized or normalized in seen:
        return
    seen.add(normalized)
    commands.append({"command": normalized, "source": source})


def _workflow_run_blocks(path: Path) -> Iterator[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", line)
        if not match:
            index += 1
            continue
        indentation = len(match.group(1))
        value = match.group(2).strip()
        if value not in {"|", ">", "|-", ">-", "|+", ">+"}:
            if value:
                yield value.strip("'\"")
            index += 1
            continue
        block: list[str] = []
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= indentation:
                break
            if candidate.strip():
                block.append(candidate.strip())
            index += 1
        if block:
            yield " && ".join(block)


def _discover_commands(root: Path, files: list[Path]) -> list[dict[str, str]]:
    commands: list[dict[str, str]] = []
    seen: set[str] = set()
    relative_files = {_relative(root, path): path for path in files}

    package_json = relative_files.get("package.json")
    if package_json:
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            test = package.get("scripts", {}).get("test")
            if isinstance(test, str) and test.strip():
                _add_command(commands, seen, "npm test", "package.json scripts.test")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass

    tests_present = any(path == "tests" or path.startswith("tests/") for path in relative_files)
    pyproject = relative_files.get("pyproject.toml")
    if tests_present and pyproject:
        try:
            content = pyproject.read_text(encoding="utf-8").lower()
        except (OSError, UnicodeDecodeError):
            content = ""
        if "pytest" in content:
            _add_command(commands, seen, "python -m pytest", "pyproject.toml and tests/")
        else:
            _add_command(
                commands,
                seen,
                "python -m unittest discover -s tests -v",
                "Python project with tests/",
            )

    manifest_commands = {
        "Cargo.toml": "cargo test",
        "go.mod": "go test ./...",
        "tox.ini": "tox",
        "noxfile.py": "nox",
    }
    for manifest, command in manifest_commands.items():
        if manifest in relative_files:
            _add_command(commands, seen, command, manifest)

    makefile = relative_files.get("Makefile")
    if makefile:
        try:
            if re.search(r"(?m)^test\s*:", makefile.read_text(encoding="utf-8")):
                _add_command(commands, seen, "make test", "Makefile test target")
        except (OSError, UnicodeDecodeError):
            pass

    workflow_files = sorted(
        path
        for relative, path in relative_files.items()
        if relative.startswith(".github/workflows/") and path.suffix in {".yml", ".yaml"}
    )
    for path in workflow_files:
        for command in _workflow_run_blocks(path):
            lowered = command.lower()
            if any(term in lowered for term in _VERIFY_TERMS):
                _add_command(commands, seen, command, _relative(root, path))
    return commands[:20]


def _discover_artifacts(root: Path, files: list[Path]) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for path in files:
        relative = _relative(root, path)
        if relative in {".epistemic-ci.json", "epistemic-ci-result.json"}:
            continue
        lowered = path.name.lower()
        if path.suffix.lower() not in _ARTIFACT_SUFFIXES:
            continue
        term = next((item for item in _ARTIFACT_TERMS if item in lowered), None)
        if term:
            artifacts.append(
                {
                    "path": relative,
                    "reason": f"filename contains '{term}'",
                }
            )
        if len(artifacts) == 50:
            break
    return artifacts


def discover_repository(
    root: Path,
    repository_name: str | None = None,
) -> dict[str, Any]:
    repository = root.resolve(strict=True)
    if not repository.is_dir():
        raise OnboardingError("root must be a directory")
    files = list(_iter_files(repository))
    workflows = sorted(
        _relative(repository, path)
        for path in files
        if _relative(repository, path).startswith(".github/workflows/")
        and path.suffix in {".yml", ".yaml"}
    )
    discovery = {
        "repository_name": repository_name or repository.name,
        "workflow_files": workflows,
        "verification_command_candidates": _discover_commands(repository, files),
        "artifact_candidates": _discover_artifacts(repository, files),
    }
    discovery["fingerprint"] = _canonical_fingerprint(discovery)
    return discovery


def _relative_answer_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OnboardingError(f"{field} entries must be non-empty strings")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise OnboardingError(f"{field} entries must be repository-relative paths")
    return path.as_posix()


def load_answers(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OnboardingError(f"cannot load onboarding answers: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != ANSWERS_SCHEMA:
        raise OnboardingError(f"answers schema must be {ANSWERS_SCHEMA}")
    if value.get("human_confirmed") is not True:
        raise OnboardingError("answers.human_confirmed must be true")
    confirmed_by = value.get("confirmed_by")
    if not isinstance(confirmed_by, str) or not confirmed_by.strip():
        raise OnboardingError("answers.confirmed_by must be a non-empty string")
    verification = value.get("verification_command")
    if (
        not isinstance(verification, list)
        or not verification
        or any(not isinstance(item, str) or not item for item in verification)
    ):
        raise OnboardingError("answers.verification_command must be a non-empty string array")
    outputs = value.get("trusted_outputs")
    if not isinstance(outputs, list) or not outputs:
        raise OnboardingError("answers.trusted_outputs must be a non-empty array")
    failures = value.get("required_failures")
    if (
        not isinstance(failures, list)
        or not failures
        or any(not isinstance(item, str) or not item.strip() for item in failures)
    ):
        raise OnboardingError("answers.required_failures must be a non-empty string array")
    population = value.get("checked_population")
    if not isinstance(population, str) or not population.strip():
        raise OnboardingError("answers.checked_population must be a non-empty string")
    normalized = {
        "schema": ANSWERS_SCHEMA,
        "human_confirmed": True,
        "confirmed_by": confirmed_by.strip(),
        "verification_command": list(verification),
        "trusted_outputs": [
            _relative_answer_path(item, "answers.trusted_outputs") for item in outputs
        ],
        "checked_population": population.strip(),
        "required_failures": [item.strip() for item in failures],
    }
    normalized["fingerprint"] = _canonical_fingerprint(normalized)
    return normalized


def _configuration_alignment(
    answers: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    vacuous = config.get("vacuous_test")
    configured_verify = vacuous.get("verify_command") if isinstance(vacuous, dict) else None
    if configured_verify != answers["verification_command"]:
        failures.append(
            "vacuous_test.verify_command does not match the human-confirmed verification command"
        )

    binding = config.get("final_artifact_binding")
    configured_paths = binding.get("artifact_paths") if isinstance(binding, dict) else None
    paths = configured_paths if isinstance(configured_paths, list) else []
    uncovered: list[str] = []
    for trusted in answers["trusted_outputs"]:
        covered = any(
            isinstance(candidate, str)
            and (
                trusted == candidate.rstrip("/")
                or trusted.startswith(candidate.rstrip("/") + "/")
            )
            for candidate in paths
            if candidate
        )
        if not covered:
            uncovered.append(trusted)
    if uncovered:
        failures.append("trusted outputs are not covered by final_artifact_binding.artifact_paths")

    return {
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "human_confirmed_verification_command": answers["verification_command"],
        "configured_verification_command": configured_verify,
        "human_confirmed_trusted_outputs": answers["trusted_outputs"],
        "configured_artifact_paths": paths,
        "uncovered_trusted_outputs": uncovered,
    }


def build_onboarding_report(
    root: Path,
    answers_path: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    discovery = discover_repository(root)
    report: dict[str, Any] = {
        "schema": ONBOARDING_SCHEMA,
        "status": "needs_human_confirmation",
        "discovery": discovery,
        "questions": [
            {
                "id": "trusted_outputs",
                "prompt": "Which final files or results do people actually trust?",
            },
            {
                "id": "required_failures",
                "prompt": "Which planted mistakes must make verification fail?",
            },
            {
                "id": "checked_population",
                "prompt": "What exact population or evidence produced the result?",
            },
        ],
        "boundary": (
            "Discovery proposes mechanics only. Human confirmation records intended meaning; "
            "it does not prove identity, truth, representativeness, or independence."
        ),
    }
    if answers_path is None:
        return report
    answers = load_answers(answers_path)
    report["human_confirmation"] = answers
    report["status"] = "needs_configuration"
    if config_path is None:
        return report
    try:
        config = load_config(config_path)
    except ConfigurationError as exc:
        raise OnboardingError(str(exc)) from exc
    validation = run_all(root, config)
    alignment = _configuration_alignment(answers, config)
    report["candidate_config"] = {
        "path": config_path.name,
        "fingerprint": _canonical_fingerprint(config),
    }
    report["validation"] = validation
    report["configuration_alignment"] = alignment
    report["status"] = "ready_for_human_review" if (
        validation["status"] == "pass" and alignment["status"] == "pass"
    ) else "validation_failed"
    return report
