from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from epistemic_ci.onboarding import (
    ANSWERS_SCHEMA,
    OnboardingError,
    build_onboarding_report,
    discover_repository,
    load_answers,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class OnboardingTestCase(unittest.TestCase):
    def test_discovery_finds_workflow_commands_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text(
                "steps:\n  - run: python -m pytest\n",
                encoding="utf-8",
            )
            (root / "results").mkdir()
            (root / "results" / "final-report.json").write_text("{}\n", encoding="utf-8")

            discovery = discover_repository(root)

            commands = [item["command"] for item in discovery["verification_command_candidates"]]
            artifacts = [item["path"] for item in discovery["artifact_candidates"]]
            self.assertIn("python -m pytest", commands)
            self.assertIn("results/final-report.json", artifacts)
            self.assertTrue(discovery["fingerprint"].startswith("sha256:"))
            self.assertNotIn(str(root), json.dumps(discovery))

    def test_answers_require_explicit_human_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answers.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": ANSWERS_SCHEMA,
                        "human_confirmed": False,
                        "confirmed_by": "owner",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(OnboardingError, "human_confirmed"):
                load_answers(path)

    def test_answers_reject_paths_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answers.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": ANSWERS_SCHEMA,
                        "human_confirmed": True,
                        "confirmed_by": "owner",
                        "verification_command": ["python3", "verify.py"],
                        "trusted_outputs": ["../private.json"],
                        "checked_population": "frozen records",
                        "required_failures": ["changed verdict"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(OnboardingError, "repository-relative"):
                load_answers(path)

    def test_complete_demo_pairing_is_ready_for_human_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "demo"
            shutil.copytree(REPOSITORY_ROOT / "examples" / "demo", root)
            answers = root / "answers.json"
            answers.write_text(
                json.dumps(
                    {
                        "schema": ANSWERS_SCHEMA,
                        "human_confirmed": True,
                        "confirmed_by": "repository owner",
                        "verification_command": ["python3", "verify.py"],
                        "trusted_outputs": ["results/result.json"],
                        "checked_population": "generated records",
                        "required_failures": ["changed verdict"],
                    }
                ),
                encoding="utf-8",
            )

            report = build_onboarding_report(root, answers, root / ".epistemic-ci.json")

            self.assertEqual(report["status"], "ready_for_human_review")
            self.assertEqual(report["validation"]["status"], "pass")
            self.assertEqual(report["configuration_alignment"]["status"], "pass")
            self.assertEqual(len(report["validation"]["checks"]), 8)

    def test_passing_config_cannot_override_human_confirmed_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "demo"
            shutil.copytree(REPOSITORY_ROOT / "examples" / "demo", root)
            answers = root / "answers.json"
            answers.write_text(
                json.dumps(
                    {
                        "schema": ANSWERS_SCHEMA,
                        "human_confirmed": True,
                        "confirmed_by": "repository owner",
                        "verification_command": ["python3", "different-verifier.py"],
                        "trusted_outputs": ["results/unbound-report.json"],
                        "checked_population": "generated records",
                        "required_failures": ["changed verdict"],
                    }
                ),
                encoding="utf-8",
            )

            report = build_onboarding_report(root, answers, root / ".epistemic-ci.json")

            self.assertEqual(report["validation"]["status"], "pass")
            self.assertEqual(report["configuration_alignment"]["status"], "fail")
            self.assertEqual(report["status"], "validation_failed")
            self.assertEqual(
                report["configuration_alignment"]["uncovered_trusted_outputs"],
                ["results/unbound-report.json"],
            )


if __name__ == "__main__":
    unittest.main()
