from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epistemic_ci.cli import main


class CLITestCase(unittest.TestCase):
    def test_missing_config_writes_fail_closed_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("builtins.print"):
                returncode = main(
                    [
                        "run",
                        "--root",
                        str(root),
                        "--config",
                        "missing.json",
                        "--output",
                        "result.json",
                    ]
                )
            self.assertEqual(returncode, 1)
            result = json.loads((root / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["checks"][0]["name"], "configuration")

    def test_init_writes_discovery_report_without_claiming_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "pyproject.toml").write_text(
                "[project]\nname = \"sample\"\n",
                encoding="utf-8",
            )
            with patch("builtins.print"):
                returncode = main(["init", "--root", str(root)])
            self.assertEqual(returncode, 0)
            report = json.loads(
                (root / "epistemic-ci-onboarding.json").read_text(encoding="utf-8")
            )
            self.assertEqual(report["status"], "needs_human_confirmation")
            self.assertNotIn("human_confirmation", report)

    def test_init_refuses_to_replace_report_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "epistemic-ci-onboarding.json"
            output.write_text("preserve me\n", encoding="utf-8")
            with patch("builtins.print"):
                returncode = main(["init", "--root", str(root)])
            self.assertEqual(returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "preserve me\n")

    def test_init_refuses_config_without_answers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("builtins.print"):
                returncode = main(
                    ["init", "--root", str(root), "--config", ".epistemic-ci.json"]
                )
            self.assertEqual(returncode, 2)
            self.assertFalse((root / "epistemic-ci-onboarding.json").exists())


if __name__ == "__main__":
    unittest.main()
