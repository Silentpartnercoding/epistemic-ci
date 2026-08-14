"""Checks 6 and 7, both questions about the SHAPE of an outcome matrix.

Check 6 asks whether a row varies at all. Check 7 asks whether two rows are
identical. Both worked instances come from the Minority Prophet programme that
proposed them, which is the best available provenance for a check: a defect that
actually happened, in code someone actually shipped.

unittest and no third-party imports: this project declares `dependencies = []`.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from epistemic_ci.core import check_control_discrimination, check_evidential_independence

PYTHON = "python3"


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class MatrixCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        write(self.root, "a.txt", "PASS\n")
        write(self.root, "b.txt", "ORIGINAL\n")
        # fires only when a.txt is broken
        write(self.root, "check_a.py",
              "import sys\nfrom pathlib import Path\n"
              "sys.exit(0 if 'PASS' in Path('a.txt').read_text() else 1)\n")
        # fires only when b.txt is broken
        write(self.root, "check_b.py",
              "import sys\nfrom pathlib import Path\n"
              "sys.exit(0 if 'ORIGINAL' in Path('b.txt').read_text() else 1)\n")
        # fires on everything -- the 44,450/44,450 shape from issue #3
        write(self.root, "always.py", "import sys\nsys.exit(1)\n")
        # never fires
        write(self.root, "never.py", "import sys\nsys.exit(0)\n")

    MUTATIONS = [
        {"name": "break-a", "path": "a.txt", "search": "PASS", "replace": "FAIL"},
        {"name": "break-b", "path": "b.txt", "search": "ORIGINAL", "replace": "CHANGED"},
    ]

    def _cfg(self, section: str, tests: list[dict]) -> dict:
        return {"version": 1, section: {"tests": tests, "mutations": self.MUTATIONS}}

    # ---- check 6 --------------------------------------------------------
    def test_a_discriminating_control_passes(self) -> None:
        cfg = self._cfg("control_discrimination",
                        [{"name": "a", "command": [PYTHON, "check_a.py"]}])
        result = check_control_discrimination(self.root, cfg)
        self.assertEqual(result.status, "pass", result.details)
        self.assertEqual(result.details["discriminating"], ["a"])

    def test_a_control_that_fires_on_everything_is_caught(self) -> None:
        """Issue #3's instance: 44,450 fired / 44,450 eligible. Not most, all --
        because the property was entailed by the definition. It was filed under
        checker power and it measured the population."""
        cfg = self._cfg("control_discrimination",
                        [{"name": "always", "command": [PYTHON, "always.py"]}])
        result = check_control_discrimination(self.root, cfg)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.details["fires_on_everything"], ["always"])

    def test_a_control_that_never_fires_is_caught(self) -> None:
        cfg = self._cfg("control_discrimination",
                        [{"name": "never", "command": [PYTHON, "never.py"]}])
        result = check_control_discrimination(self.root, cfg)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.details["never_fires"], ["never"])

    # ---- check 7 --------------------------------------------------------
    def test_two_separated_tests_pass(self) -> None:
        cfg = self._cfg("evidential_independence", [
            {"name": "a", "command": [PYTHON, "check_a.py"]},
            {"name": "b", "command": [PYTHON, "check_b.py"]},
        ])
        result = check_evidential_independence(self.root, cfg)
        self.assertEqual(result.status, "pass", result.details)
        self.assertEqual(result.details["indistinguishable_pairs"], [])

    def test_two_tests_with_identical_fire_patterns_are_flagged(self) -> None:
        """Issue #4's instance: a lemma cited as separate evidence for a theorem
        it was a corollary of. Plant-a-defect cannot see it, because the implied
        test does fail when the implying one fails."""
        cfg = self._cfg("evidential_independence", [
            {"name": "a", "command": [PYTHON, "check_a.py"]},
            {"name": "a-again", "command": [PYTHON, "check_a.py"]},
        ])
        result = check_evidential_independence(self.root, cfg)
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.details["indistinguishable_pairs"], [["a", "a-again"]])

    def test_the_result_does_not_claim_implication_it_cannot_decide(self) -> None:
        """Identical patterns are evidence of nothing separating them, not proof
        that one implies the other. Deciding implication is undecidable and the
        check does not pretend otherwise."""
        cfg = self._cfg("evidential_independence", [
            {"name": "a", "command": [PYTHON, "check_a.py"]},
            {"name": "a-again", "command": [PYTHON, "check_a.py"]},
        ])
        result = check_evidential_independence(self.root, cfg)
        self.assertIn("do not prove", result.details["note"])

    def test_independence_needs_a_pair(self) -> None:
        cfg = self._cfg("evidential_independence",
                        [{"name": "a", "command": [PYTHON, "check_a.py"]}])
        result = check_evidential_independence(self.root, cfg)
        self.assertEqual(result.status, "fail")
        self.assertIn("at least two", result.reason)

    # ---- shared ---------------------------------------------------------
    def test_absent_sections_do_not_break_existing_configs_but_say_so(self) -> None:
        for check in (check_control_discrimination, check_evidential_independence):
            result = check(self.root, {"version": 1})
            self.assertEqual(result.status, "pass")
            self.assertTrue(result.details["vacuous"])
            self.assertIn("establishes nothing", result.reason)


if __name__ == "__main__":
    unittest.main()
