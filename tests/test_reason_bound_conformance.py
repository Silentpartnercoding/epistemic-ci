"""Check 9: a negative conformance verdict must come from its target property."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from epistemic_ci.core import _assurance_bound, check_reason_bound_conformance


PYTHON = sys.executable


def write_observation(path: Path, observation: object) -> None:
    path.write_text(
        f"import json\nprint(json.dumps({observation!r}))\n",
        encoding="utf-8",
    )


class ReasonBoundConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.expected = {
            "verdict": "reject",
            "property_under_test": "manifest_membership_binding",
            "property_reached": True,
            "stop_reason": "DECLARATION_NOT_IN_MANIFEST",
        }
        self.mutant = {
            "verdict": "reject",
            "property_under_test": "manifest_membership_binding",
            "property_reached": False,
            "stop_reason": "UNSUPPORTED_VERSION",
        }
        write_observation(self.root / "reference.py", self.expected)
        write_observation(self.root / "mutant.py", self.mutant)
        write_observation(self.root / "survivor.py", self.expected)
        write_observation(
            self.root / "wrong-verdict.py",
            {**self.mutant, "verdict": "allow"},
        )
        (self.root / "malformed.py").write_text("print('not json')\n", encoding="utf-8")

    def config(self) -> dict:
        return {
            "version": 1,
            "reason_bound_conformance": {
                "cases": [
                    {
                        "name": "CONFORMANCE-CAUSALITY-001",
                        "expected": self.expected,
                        "reference_command": [PYTHON, "reference.py"],
                        "mutants": [
                            {
                                "name": "short-circuit-version-guard",
                                "command": [PYTHON, "mutant.py"],
                            }
                        ],
                    }
                ]
            },
        }

    def test_verdict_only_false_green_is_killed_by_reason_bound_vector(self) -> None:
        result = check_reason_bound_conformance(self.root, self.config())

        self.assertEqual(result.status, "pass", result.details)
        self.assertEqual(
            result.details["killed"],
            ["CONFORMANCE-CAUSALITY-001:short-circuit-version-guard"],
        )
        mutant = result.details["cases"][0]["mutants"][0]
        self.assertTrue(mutant["verdict_only_passes"])
        self.assertFalse(mutant["reason_bound_passes"])
        self.assertFalse(mutant["observed"]["property_reached"])

    def test_a_mutant_that_survives_the_reason_bound_contract_fails(self) -> None:
        config = self.config()
        config["reason_bound_conformance"]["cases"][0]["mutants"][0]["command"] = [
            PYTHON,
            "survivor.py",
        ]

        result = check_reason_bound_conformance(self.root, config)

        self.assertEqual(result.status, "fail")
        self.assertEqual(
            result.details["survivors"],
            ["CONFORMANCE-CAUSALITY-001:short-circuit-version-guard"],
        )

    def test_a_mutant_that_changes_the_verdict_does_not_prove_discrimination(self) -> None:
        config = self.config()
        config["reason_bound_conformance"]["cases"][0]["mutants"][0]["command"] = [
            PYTHON,
            "wrong-verdict.py",
        ]

        result = check_reason_bound_conformance(self.root, config)

        self.assertEqual(result.status, "fail")
        self.assertEqual(
            result.details["nonqualifying_mutants"],
            ["CONFORMANCE-CAUSALITY-001:short-circuit-version-guard"],
        )

    def test_the_reference_must_match_the_reason_bound_contract(self) -> None:
        config = self.config()
        config["reason_bound_conformance"]["cases"][0]["reference_command"] = [
            PYTHON,
            "mutant.py",
        ]

        result = check_reason_bound_conformance(self.root, config)

        self.assertEqual(result.status, "fail")
        self.assertEqual(
            result.details["reference_mismatches"],
            ["CONFORMANCE-CAUSALITY-001"],
        )

    def test_the_expected_contract_must_require_property_reachability(self) -> None:
        config = self.config()
        config["reason_bound_conformance"]["cases"][0]["expected"][
            "property_reached"
        ] = False

        result = check_reason_bound_conformance(self.root, config)

        self.assertEqual(result.status, "fail")
        self.assertIn("must be true", result.details["invalid"][0])

    def test_command_output_must_be_one_json_observation(self) -> None:
        config = self.config()
        config["reason_bound_conformance"]["cases"][0]["reference_command"] = [
            PYTHON,
            "malformed.py",
        ]

        result = check_reason_bound_conformance(self.root, config)

        self.assertEqual(result.status, "fail")
        self.assertIn("one JSON object", result.details["invalid"][0])

    def test_absent_section_is_explicitly_vacuous(self) -> None:
        result = check_reason_bound_conformance(self.root, {"version": 1})

        self.assertEqual(result.status, "pass")
        self.assertTrue(result.details["vacuous"])
        self.assertIn("establishes nothing", result.reason)

    def test_assurance_bound_counts_cases_and_mutants_separately(self) -> None:
        bound = _assurance_bound(self.config())

        self.assertEqual(
            bound["reason_bound_conformance"],
            {"declared_cases": 1, "declared_mutants": 1},
        )
        self.assertIn("wrong execution paths", bound["does_not_establish"])


if __name__ == "__main__":
    unittest.main()
