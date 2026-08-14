"""Check 8: the population must be able to exhibit the effect.

Every other check interrogates the verification path. This one interrogates the
POPULATION, and it is the only failure no amount of checking the checker can
find -- planting a defect does make verification fail, and the verifier is sound.
The corpus simply has no instances of the thing the endpoint measures.

Issue #2's instance, reproduced below as `test_the_worked_instance_shape`:
208 searched, 0 not_searched. Positive count, valid fingerprints, all checks
green, and the endpoint structurally unable to move.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from epistemic_ci.core import check_effect_reachability

PYTHON = "python3"


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class EffectReachabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        write(self.root, "count_searched.py", "print(208)\n")
        write(self.root, "count_not_searched.py", "print(0)\n")
        write(self.root, "count_some_not_searched.py", "print(17)\n")
        write(self.root, "broken.py", "import sys\nsys.exit(3)\n")
        write(self.root, "not_a_number.py", "print('lots')\n")

    def _cfg(self, strata: list[dict]) -> dict:
        return {"version": 1,
                "effect_reachability": {"endpoint": "false_clean_rate", "strata": strata}}

    def test_the_worked_instance_shape(self) -> None:
        """208 searched, 0 not-searched. A positive population that cannot move
        the endpoint, because the mechanism's only lever is never pulled."""
        result = check_effect_reachability(self.root, self._cfg([
            {"name": "searched", "count_command": [PYTHON, "count_searched.py"]},
            {"name": "not_searched", "count_command": [PYTHON, "count_not_searched.py"]},
        ]))
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.details["counts"], {"searched": 208, "not_searched": 0})
        self.assertIn("not_searched=0", result.details["understocked_strata"][0])

    def test_a_population_stocked_on_both_sides_passes(self) -> None:
        result = check_effect_reachability(self.root, self._cfg([
            {"name": "searched", "count_command": [PYTHON, "count_searched.py"]},
            {"name": "not_searched", "count_command": [PYTHON, "count_some_not_searched.py"]},
        ]))
        self.assertEqual(result.status, "pass", result.details)
        self.assertEqual(result.details["counts"], {"searched": 208, "not_searched": 17})

    def test_a_single_positive_count_is_not_enough(self) -> None:
        """The issue proposed one predicate returning > 0. That passes the
        worked instance, because 208 > 0. Strata are why this check catches it."""
        single = check_effect_reachability(self.root, self._cfg([
            {"name": "searched", "count_command": [PYTHON, "count_searched.py"]},
        ]))
        self.assertEqual(single.status, "pass")  # a lone positive count says nothing
        both = check_effect_reachability(self.root, self._cfg([
            {"name": "searched", "count_command": [PYTHON, "count_searched.py"]},
            {"name": "not_searched", "count_command": [PYTHON, "count_not_searched.py"]},
        ]))
        self.assertEqual(both.status, "fail")

    def test_a_higher_minimum_can_be_required(self) -> None:
        result = check_effect_reachability(self.root, self._cfg([
            {"name": "not_searched", "count_command": [PYTHON, "count_some_not_searched.py"],
             "minimum_instances": 50},
        ]))
        self.assertEqual(result.status, "fail")
        self.assertIn("needs >= 50", result.details["understocked_strata"][0])

    def test_a_count_command_that_fails_is_invalid_not_zero(self) -> None:
        result = check_effect_reachability(self.root, self._cfg([
            {"name": "broken", "count_command": [PYTHON, "broken.py"]},
        ]))
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("failed to run" in i for i in result.details["invalid"]))

    def test_a_non_numeric_count_is_rejected(self) -> None:
        result = check_effect_reachability(self.root, self._cfg([
            {"name": "vague", "count_command": [PYTHON, "not_a_number.py"]},
        ]))
        self.assertEqual(result.status, "fail")
        self.assertTrue(any("integer count" in i for i in result.details["invalid"]))

    def test_the_declaration_bound_is_reported_not_hidden(self) -> None:
        result = check_effect_reachability(self.root, self._cfg([
            {"name": "searched", "count_command": [PYTHON, "count_searched.py"]},
        ]))
        self.assertIn("declared only the strata it happens to contain",
                      result.details["bounded_by"])

    def test_absent_section_does_not_break_existing_configs_but_says_so(self) -> None:
        result = check_effect_reachability(self.root, {"version": 1})
        self.assertEqual(result.status, "pass")
        self.assertTrue(result.details["vacuous"])
        self.assertIn("establishes nothing", result.reason)


if __name__ == "__main__":
    unittest.main()
