from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import pathlib
import unittest

from epistemic_ci import core

from epistemic_ci.core import (
    BINDING_SCHEMA,
    OBSERVATION_SCHEMA,
    check_executable_pass_condition,
    check_final_artifact_binding,
    check_observation_surface,
    check_vacuous_test,
    load_config,
    run_all,
)


PYTHON = sys.executable


class EpistemicCITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        (self.root / "fixture.txt").write_text("PASS\n", encoding="utf-8")
        (self.root / "generate.py").write_text(
            "from pathlib import Path\n"
            "v=Path('fixture.txt').read_text().strip()\n"
            "Path('results').mkdir(exist_ok=True)\n"
            "Path('results/out.txt').write_text('generated:'+v)\n",
            encoding="utf-8",
        )
        (self.root / "check.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "p=Path('results/out.txt')\n"
            "sys.exit(0 if p.is_file() and p.read_text()=='generated:PASS' else 1)\n",
            encoding="utf-8",
        )
        (self.root / "verify.py").write_text(
            "exec(open('generate.py').read())\nexec(open('check.py').read())\n",
            encoding="utf-8",
        )
        (self.root / "observe.py").write_text(self.valid_observation_source(), encoding="utf-8")
        (self.root / "bind.py").write_text(
            "import hashlib,json\nfrom pathlib import Path\n"
            "exec(open('generate.py').read())\n"
            "p=Path('results/out.txt')\n"
            "v={'schema':'epistemic-ci.final-artifact-binding.v1','run_id':'test-run',"
            "'artifacts':[{'path':'results/out.txt','sha256':'sha256:'"
            "+hashlib.sha256(p.read_bytes()).hexdigest()}]}\n"
            "Path('results/binding.json').write_text(json.dumps(v,sort_keys=True)+'\\n')\n",
            encoding="utf-8",
        )
        (self.root / "verify_binding.py").write_text(
            "import hashlib,json,sys\nfrom pathlib import Path\n"
            "try:\n"
            " r=json.loads(Path('results/binding.json').read_text())\n"
            " a=r['artifacts']\n"
            " ok=(r['schema']=='epistemic-ci.final-artifact-binding.v1' and len(a)==1 "
            "and a[0]['path']=='results/out.txt' and a[0]['sha256']=='sha256:'"
            "+hashlib.sha256(Path(a[0]['path']).read_bytes()).hexdigest())\n"
            "except Exception:\n ok=False\n"
            "sys.exit(0 if ok else 1)\n",
            encoding="utf-8",
        )

        (self.root / "meta.txt").write_text("ORIGINAL\n", encoding="utf-8")
        (self.root / "count_pass.py").write_text("print(3)\n", encoding="utf-8")
        (self.root / "count_fail.py").write_text("print(2)\n", encoding="utf-8")
        (self.root / "check_a.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.exit(0 if 'PASS' in Path('fixture.txt').read_text() else 1)\n",
            encoding="utf-8",
        )
        (self.root / "check_b.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "sys.exit(0 if 'ORIGINAL' in Path('meta.txt').read_text() else 1)\n",
            encoding="utf-8",
        )
        (self.root / "pinned.txt").write_text("CANONICAL\n", encoding="utf-8")
        pin_dir = self.root / ".pin"
        pin_dir.mkdir(exist_ok=True)
        (pin_dir / "pinned.txt").write_text("CANONICAL\n", encoding="utf-8")
        (self.root / "run_pinned.py").write_text(
            "from pathlib import Path\n"
            "Path('results').mkdir(exist_ok=True)\n"
            "Path('results/pinned-out.txt').write_text(Path('.pin/pinned.txt').read_text())\n",
            encoding="utf-8",
        )

    @staticmethod
    def valid_observation_source(count: int = 1) -> str:
        population = hashlib.sha256(b"population").hexdigest()
        result = hashlib.sha256(b"result").hexdigest()
        value = {
            "schema": OBSERVATION_SCHEMA,
            "run_id": "test-run",
            "population": {"count": count, "fingerprint": f"sha256:{population}"},
            "result": {"fingerprint": f"sha256:{result}"},
        }
        return f"import json\nprint(json.dumps({value!r}))\n"

    def config(self) -> dict:
        return {
            "version": 1,
            "vacuous_test": {
                "verify_command": [PYTHON, "verify.py"],
                "mutations": [
                    {
                        "name": "flip-source",
                        "path": "fixture.txt",
                        "search": "PASS",
                        "replace": "FAIL",
                    }
                ],
            },
            "executable_pass_condition": {
                "prepare_command": [PYTHON, "generate.py"],
                "check_command": [PYTHON, "check.py"],
                "generated_paths": ["results/out.txt"],
                "mutations": [
                    {
                        "name": "corrupt-output",
                        "path": "results/out.txt",
                        "search": "generated:PASS",
                        "replace": "generated:FAIL",
                    }
                ],
            },
            "observation_surface": {"command": [PYTHON, "observe.py"]},
            "final_artifact_binding": {
                "prepare_command": [PYTHON, "bind.py"],
                "verify_command": [PYTHON, "verify_binding.py"],
                "artifact_paths": ["results/out.txt"],
                "receipt_path": "results/binding.json",
            },
            # Exercised, not left vacuous. A reference configuration that skipped
            # check 5 would ship an example of the very omission the check exists
            # to detect. `pinned.txt` is the working copy; `.pin/pinned.txt` is
            # the immutable one the runner actually reads.
            # Exercised, not vacuous: check_a fires only on the fixture mutation
            # and check_b only on the meta mutation, so each control both fires
            # and does not fire, and the two are separated by a mutation.
            # Exercised, not vacuous: the endpoint depends on a pass/fail
            # distinction, and the population holds instances of both. A corpus
            # with 3 passes and 0 fails would be positive and still unable to
            # move the endpoint -- which is the shape this check exists for.
            "effect_reachability": {
                "endpoint": "demo_discrimination_rate",
                "strata": [
                    {"name": "passing", "count_command": [PYTHON, "count_pass.py"]},
                    {"name": "failing", "count_command": [PYTHON, "count_fail.py"]},
                ],
            },
            "control_discrimination": {
                "tests": [
                    {"name": "fixture-control", "command": [PYTHON, "check_a.py"]},
                    {"name": "meta-control", "command": [PYTHON, "check_b.py"]},
                ],
                "mutations": [
                    {"name": "flip-fixture", "path": "fixture.txt",
                     "search": "PASS", "replace": "FAIL"},
                    {"name": "flip-meta", "path": "meta.txt",
                     "search": "ORIGINAL", "replace": "CHANGED"},
                ],
            },
            "evidential_independence": {
                "tests": [
                    {"name": "fixture-control", "command": [PYTHON, "check_a.py"]},
                    {"name": "meta-control", "command": [PYTHON, "check_b.py"]},
                ],
                "mutations": [
                    {"name": "flip-fixture", "path": "fixture.txt",
                     "search": "PASS", "replace": "FAIL"},
                    {"name": "flip-meta", "path": "meta.txt",
                     "search": "ORIGINAL", "replace": "CHANGED"},
                ],
            },
            "pinned_input_binding": {
                "run_command": [PYTHON, "run_pinned.py"],
                "result_paths": ["results/pinned-out.txt"],
                "pins": [
                    {
                        "name": "reads-the-pin-not-the-workspace",
                        "path": "pinned.txt",
                        "search": "CANONICAL",
                        "replace": "TAMPERED",
                    }
                ],
            },
        }

    def test_all_checks_pass_without_modifying_source_workspace(self) -> None:
        result = run_all(self.root, self.config())
        self.assertEqual(result["status"], "pass")
        self.assertEqual([item["status"] for item in result["checks"]], ["pass"] * 9)
        self.assertEqual((self.root / "fixture.txt").read_text(), "PASS\n")
        self.assertFalse((self.root / "results").exists())

    def test_any_surviving_source_mutation_fails_closed(self) -> None:
        (self.root / "metadata.txt").write_text("ORIGINAL", encoding="utf-8")
        config = self.config()
        config["vacuous_test"]["mutations"].append(
            {
                "name": "survivor",
                "path": "metadata.txt",
                "search": "ORIGINAL",
                "replace": "CORRUPTED",
            }
        )
        check = check_vacuous_test(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.details["survivors"], ["survivor"])

    def test_source_mutation_must_match_exactly_once(self) -> None:
        (self.root / "unused.txt").write_text("TOKEN TOKEN", encoding="utf-8")
        config = self.config()
        config["vacuous_test"]["mutations"][0].update(
            {"path": "unused.txt", "search": "TOKEN", "replace": "OTHER"}
        )
        check = check_vacuous_test(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertTrue(check.details["invalid"])

    def test_source_mutation_cannot_escape_root(self) -> None:
        outside = self.root.parent / "outside.txt"
        outside.write_text("PASS", encoding="utf-8")
        config = self.config()
        config["vacuous_test"]["mutations"][0]["path"] = "../outside.txt"
        check = check_vacuous_test(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertEqual(outside.read_text(), "PASS")

    def test_source_mutation_cannot_follow_symlink_outside_root(self) -> None:
        outside = self.root.parent / "outside.txt"
        outside.write_text("PASS", encoding="utf-8")
        try:
            (self.root / "link.txt").symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        config = self.config()
        config["vacuous_test"]["mutations"][0]["path"] = "link.txt"
        check = check_vacuous_test(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertEqual(outside.read_text(), "PASS")

    def test_output_change_alone_does_not_prove_dependency(self) -> None:
        (self.root / "check.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        check = check_executable_pass_condition(self.root, self.config())
        self.assertEqual(check.status, "fail")
        self.assertEqual(check.details["survivors"], ["corrupt-output"])

    def test_deterministic_generated_output_is_accepted(self) -> None:
        first = check_executable_pass_condition(self.root, self.config())
        second = check_executable_pass_condition(self.root, self.config())
        self.assertEqual(first.status, "pass")
        self.assertEqual(second.status, "pass")
        self.assertEqual(
            first.details["generated_fingerprint"],
            second.details["generated_fingerprint"],
        )

    def test_output_mutation_must_target_declared_generated_file(self) -> None:
        config = self.config()
        config["executable_pass_condition"]["mutations"][0]["path"] = "fixture.txt"
        check = check_executable_pass_condition(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertTrue(check.details["invalid"])

    def test_generated_paths_must_match_files(self) -> None:
        config = self.config()
        config["executable_pass_condition"]["generated_paths"] = ["missing.txt"]
        check = check_executable_pass_condition(self.root, config)
        self.assertEqual(check.status, "fail")

    def test_observation_requires_json(self) -> None:
        (self.root / "observe.py").write_text("print('banana')\n", encoding="utf-8")
        check = check_observation_surface(self.root, self.config())
        self.assertEqual(check.status, "fail")

    def test_observation_requires_positive_population(self) -> None:
        (self.root / "observe.py").write_text(self.valid_observation_source(0), encoding="utf-8")
        check = check_observation_surface(self.root, self.config())
        self.assertEqual(check.status, "fail")

    def test_observation_requires_sha256_fingerprints(self) -> None:
        config = self.config()
        (self.root / "observe.py").write_text(
            "import json\nprint(json.dumps({"
            f"'schema':'{OBSERVATION_SCHEMA}','run_id':'x',"
            "'population':{'count':1,'fingerprint':'hello'},"
            "'result':{'fingerprint':'sha256:'+'0'*64}}))\n",
            encoding="utf-8",
        )
        check = check_observation_surface(self.root, config)
        self.assertEqual(check.status, "fail")

    def test_observation_returns_binding_fingerprint(self) -> None:
        check = check_observation_surface(self.root, self.config())
        self.assertEqual(check.status, "pass")
        self.assertRegex(check.details["observation_fingerprint"], r"^sha256:[0-9a-f]{64}$")

    def test_final_artifact_binding_rejects_stale_artifact(self) -> None:
        check = check_final_artifact_binding(self.root, self.config())
        self.assertEqual(check.status, "pass")
        self.assertEqual(
            check.details["killed"],
            ["alter-artifact:results/out.txt", "tamper-receipt-digest"],
        )

    def test_final_artifact_binding_detects_vacuous_verifier(self) -> None:
        (self.root / "verify_binding.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        check = check_final_artifact_binding(self.root, self.config())
        self.assertEqual(check.status, "fail")
        self.assertEqual(
            check.details["survivors"],
            ["alter-artifact:results/out.txt", "tamper-receipt-digest"],
        )

    def test_final_artifact_binding_rejects_verifier_that_rewrites_evidence(self) -> None:
        (self.root / "verify_binding.py").write_text(
            "import hashlib,json\nfrom pathlib import Path\n"
            "p=Path('results/out.txt')\n"
            "p.write_bytes(p.read_bytes()+b'rewritten')\n"
            "r=json.loads(Path('results/binding.json').read_text())\n"
            "r['artifacts'][0]['sha256']='sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()\n"
            "Path('results/binding.json').write_text(json.dumps(r))\n",
            encoding="utf-8",
        )
        check = check_final_artifact_binding(self.root, self.config())
        self.assertEqual(check.status, "fail")
        self.assertIn("changed", check.reason)

    def test_final_artifact_binding_requires_exact_receipt_coverage(self) -> None:
        (self.root / "extra.txt").write_text("second artifact", encoding="utf-8")
        config = self.config()
        config["final_artifact_binding"]["artifact_paths"].append("extra.txt")
        check = check_final_artifact_binding(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertIn("exactly match", check.reason)

    def test_final_artifact_binding_forbids_self_inclusion(self) -> None:
        config = self.config()
        config["final_artifact_binding"]["artifact_paths"].append("results/binding.json")
        check = check_final_artifact_binding(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertIn("outside artifact_paths", check.reason)

    def test_final_artifact_binding_rejects_wrong_schema(self) -> None:
        source = (self.root / "bind.py").read_text(encoding="utf-8")
        (self.root / "bind.py").write_text(
            source.replace(BINDING_SCHEMA, "epistemic-ci.wrong.v1"),
            encoding="utf-8",
        )
        check = check_final_artifact_binding(self.root, self.config())
        self.assertEqual(check.status, "fail")
        self.assertIn("schema", check.reason)

    def test_string_commands_are_rejected(self) -> None:
        config = self.config()
        config["vacuous_test"]["verify_command"] = f"{PYTHON} verify.py"
        check = check_vacuous_test(self.root, config)
        self.assertEqual(check.status, "fail")

    def test_command_timeout_fails(self) -> None:
        (self.root / "slow.py").write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
        config = self.config()
        config["vacuous_test"]["verify_command"] = [PYTHON, "slow.py"]
        config["vacuous_test"]["timeout_seconds"] = 1
        check = check_vacuous_test(self.root, config)
        self.assertEqual(check.status, "fail")
        self.assertTrue(check.details["timed_out"])

    def test_any_failed_check_fails_overall_result(self) -> None:
        config = self.config()
        config["observation_surface"]["command"] = [PYTHON, "missing.py"]
        result = run_all(self.root, config)
        self.assertEqual(result["status"], "fail")

    def test_version_is_required(self) -> None:
        config = self.config()
        config.pop("version")
        result = run_all(self.root, config)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["checks"][0]["name"], "configuration")

    def test_invalid_json_config_is_rejected(self) -> None:
        path = self.root / "bad.json"
        path.write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_config(path)


if __name__ == "__main__":
    unittest.main()


class AssuranceBoundTests(unittest.TestCase):
    """ECI-01. A passing run must carry its own limit.

    Each check's reason already says "every DECLARED mutation". The top-level
    status does not, and that is the field a badge or a summary reads. A green
    result is compatible with a verifier that only detects the defects its author
    chose to declare -- demonstrated by a package whose verifier checks nothing
    but that its input file is non-empty, which passes all four checks and then
    accepts a flipped verdict.

    The bound is reported, not enforced: whether a declared mutation set is
    representative cannot be decided without knowing which defects matter, which
    is the thing under study.
    """

    def test_a_passing_result_states_what_it_does_not_establish(self) -> None:
        config = _demo_config()
        bound = core._assurance_bound(config)
        self.assertGreater(bound["declared_mutations_total"], 0)
        self.assertIn("not declared", bound["does_not_establish"])
        self.assertIn("representative", bound["does_not_establish"])

    def test_the_bound_counts_the_mutations_actually_declared(self) -> None:
        config = _demo_config()
        config["vacuous_test"]["mutations"] = [
            {"name": "a", "path": "f", "search": "x", "replace": "y"},
            {"name": "b", "path": "f", "search": "p", "replace": "q"},
        ]
        bound = core._assurance_bound(config)
        self.assertEqual(bound["declared_mutations"]["vacuous_test"], 2)

    def test_the_bound_is_present_in_the_result_document(self) -> None:
        """It must survive into the artifact, not only exist as a function."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "x.txt").write_text("hello\n", encoding="utf-8")
            result = core.run_all(root, {"version": 1})
            self.assertIn("assurance_bound", result)
            self.assertIn("does_not_establish", result["assurance_bound"])


def _demo_config() -> dict:
    return {
        "version": 1,
        "vacuous_test": {
            "verify_command": ["true"],
            "mutations": [{"name": "m", "path": "f", "search": "a", "replace": "b"}],
        },
        "executable_pass_condition": {
            "prepare_command": ["true"], "check_command": ["true"],
            "generated_paths": ["out"],
            "mutations": [{"name": "n", "path": "out", "search": "a", "replace": "b"}],
        },
    }
