from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from epistemic_ci.core import load_config, run_all


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples/vacuous-green"


class VacuousGreenDemoTests(unittest.TestCase):
    def test_ordinary_ci_is_green_while_epistemic_ci_detects_vacuity(self) -> None:
        ordinary = subprocess.run(
            [sys.executable, "ordinary_ci.py"],
            cwd=DEMO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ordinary.returncode, 0)
        self.assertIn("ORDINARY CI: PASS", ordinary.stdout)

        result = run_all(DEMO, load_config(DEMO / ".epistemic-ci.json"))
        checks = {check["name"]: check for check in result["checks"]}

        self.assertEqual(result["status"], "fail")
        self.assertEqual(checks["vacuous-test"]["status"], "fail")
        self.assertEqual(
            checks["vacuous-test"]["details"]["survivors"],
            ["change-source-verdict"],
        )
        self.assertEqual(checks["executable-pass-condition"]["status"], "pass")
        self.assertEqual(checks["observation-surface"]["status"], "pass")
        self.assertEqual(checks["final-artifact-binding"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
