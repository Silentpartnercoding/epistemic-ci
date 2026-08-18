"""The three fixtures must each fail exactly one check, and no other.

A fixture that fails several checks demonstrates an incomplete configuration
rather than the defect it is about. These tests pin the discrimination: ordinary
verification is green, seven checks pass, and exactly one refuses.

They also pin the *reason*. A fixture that started failing its target check for
an unrelated cause would still pass a count-only assertion.

Written with unittest and no third-party imports, for the same reason as
test_pinned_input_binding: this project declares `dependencies = []` and CI runs
`python -m unittest discover`. A pytest-parametrized draft of this file failed
twice over -- the import broke CI on all four supported Python versions, and had
pytest been installed instead, `unittest discover` would have collected nothing
from it and reported green. A regression test that cannot run is the exact
failure this repository is about.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

CASES = [
    ("empty-stratum", "effect-reachability", "cannot exhibit the effect"),
    ("pin-drift", "pinned-input-binding", "leave the result unchanged"),
    ("one-witness", "evidential-independence", "separated by at least one declared mutation"),
]


def _run_gate(fixture: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "epistemic_ci.cli", "run",
         "--root", str(ROOT / "examples" / fixture), "--config", ".epistemic-ci.json"],
        capture_output=True, text=True, cwd=ROOT, timeout=600,
    )
    return json.loads(proc.stdout)


class FailureClassFixtureTests(unittest.TestCase):

    def test_each_fixture_fails_exactly_its_target_check(self):
        for fixture, target, phrase in CASES:
            with self.subTest(fixture=fixture):
                result = _run_gate(fixture)
                failing = {c["name"]: c for c in result["checks"] if c["status"] != "pass"}
                self.assertEqual(
                    list(failing), [target],
                    f"{fixture} should fail only {target}; failed {sorted(failing)}")
                self.assertIn(
                    phrase, failing[target]["reason"],
                    f"{fixture} failed {target} for an unexpected reason: "
                    f"{failing[target]['reason']}")
                self.assertEqual(result["status"], "fail")

    def test_ordinary_verification_is_green(self):
        """The whole point: ordinary CI passes on every one of these."""
        for fixture, _target, _phrase in CASES:
            with self.subTest(fixture=fixture):
                proc = subprocess.run(
                    [sys.executable, "verify.py"],
                    cwd=ROOT / "examples" / fixture,
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(
                    proc.returncode, 0,
                    f"{fixture}: ordinary verification should pass\n{proc.stdout}{proc.stderr}")
                self.assertIn("PASS", proc.stdout)

    def test_the_three_targets_are_distinct(self):
        """Three fixtures, three different checks. If two collapsed onto one check
        the set would demonstrate less than it claims."""
        self.assertEqual(len({target for _, target, _ in CASES}), 3)


if __name__ == "__main__":
    unittest.main()
