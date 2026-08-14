"""The fifth check: a declared-pinned input must be read from its pin.

Motivated by a real defect, not by symmetry. Minority Prophet's
canonical-capability-runner.py pinned two files at a commit, recorded their
hashes in a published result, and then hashed and EXECUTED the working-tree
copies. It agreed with the pin exactly as long as nobody edited those files.

Written with unittest and no third-party imports: this project declares
`dependencies = []` and CI runs `python -m unittest discover`. An earlier draft
of this file used pytest and broke CI on all four supported Python versions --
a dependency added to a deliberately dependency-free project.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from epistemic_ci.core import check_pinned_input_binding, run_all


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_project(base: Path, *, pinned: bool) -> Path:
    """A runner that either reads the pin (correct) or the workspace (the bug).

    The pin is modelled as a store the working copy does not overlap, which is
    what a git commit object actually is. `.git` itself is excluded from the
    isolated workspace, so a literal `git show` pin cannot be exercised here --
    a real limitation of this check, recorded in the README.
    """
    root = base / "project"
    root.mkdir()
    write(root, "source.txt", "CANONICAL\n")       # the working copy, mutated
    write(root, ".pin/source.txt", "CANONICAL\n")  # the pinned bytes, not mutated
    read = 'open(".pin/source.txt").read()' if pinned else 'open("source.txt").read()'
    write(root, "run.py", f"open('result.txt','w').write({read})\n")
    return root


CONFIG = {
    "version": 1,
    "pinned_input_binding": {
        "run_command": ["python3", "run.py"],
        "result_paths": ["result.txt"],
        "timeout_seconds": 60,
        "pins": [
            {
                "name": "source-pinned-at-commit",
                "path": "source.txt",
                "search": "CANONICAL",
                "replace": "TAMPERED",
            }
        ],
    },
}


class PinnedInputBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_a_runner_that_reads_the_pin_passes(self) -> None:
        result = check_pinned_input_binding(make_project(self.base, pinned=True), CONFIG)
        self.assertEqual(result.status, "pass", result.details)
        self.assertEqual(result.details["held"], ["source-pinned-at-commit"])

    def test_a_runner_that_reads_the_workspace_is_caught(self) -> None:
        """The exact defect. Every recorded digest would still match, because
        the digest is taken of the same copy that was executed."""
        result = check_pinned_input_binding(make_project(self.base, pinned=False), CONFIG)
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("live, not pinned" in e for e in result.details["moved"]))

    def test_declaring_a_path_as_both_live_and_pinned_is_rejected(self) -> None:
        """THE RECONCILIATION. vacuous-test requires corruption to FAIL the run;
        this check requires it to leave the result UNCHANGED. A path declared to
        both is a contradiction, rejected rather than silently resolved."""
        config = dict(CONFIG)
        config["vacuous_test"] = {
            "verify_command": ["true"],
            "timeout_seconds": 60,
            "mutations": [
                {"name": "same-file", "path": "source.txt",
                 "search": "CANONICAL", "replace": "X"}
            ],
        }
        result = check_pinned_input_binding(make_project(self.base, pinned=True), config)
        self.assertEqual(result.status, "fail")
        self.assertIn("never both", result.reason)

    def test_sensitivity_is_reported_unestablished_rather_than_assumed(self) -> None:
        """Insensitivity is generic. Sensitivity depends on the pin mechanism,
        so without a tamper_command it is reported, never assumed."""
        result = check_pinned_input_binding(make_project(self.base, pinned=True), CONFIG)
        self.assertEqual(result.details["sensitivity_not_established"],
                         ["source-pinned-at-commit"])
        self.assertEqual(result.details["sensitivity_established"], [])

    def test_absent_section_does_not_break_existing_configs_but_says_so(self) -> None:
        result = check_pinned_input_binding(make_project(self.base, pinned=True), {"version": 1})
        self.assertEqual(result.status, "pass")
        self.assertTrue(result.details["vacuous"])
        self.assertIn("establishes nothing", result.reason)

    def test_assurance_bound_counts_pins_separately_from_mutations(self) -> None:
        report = run_all(make_project(self.base, pinned=True), CONFIG)
        bound = json.loads(json.dumps(report["assurance_bound"]))
        self.assertEqual(bound["pinned_inputs"]["declared"], 1)
        self.assertEqual(bound["pinned_inputs"]["with_sensitivity_check"], 0)
        self.assertNotIn("pinned_inputs_declared", bound["declared_mutations"])


if __name__ == "__main__":
    unittest.main()
