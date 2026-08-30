"""Check 10: a harness report must vary with the outcome it summarizes."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from epistemic_ci.core import _assurance_bound, check_report_discrimination


PYTHON = sys.executable


def write_reporter(path: Path, summaries: dict[str, dict], failed_exit: int = 0) -> None:
    path.write_text(
        "import json, sys\n"
        f"summaries = {summaries!r}\n"
        "state = sys.argv[1]\n"
        "print(json.dumps(summaries[state], sort_keys=True))\n"
        f"sys.exit({failed_exit} if state == 'failed' else 0)\n",
        encoding="utf-8",
    )


class ReportDiscriminationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.summaries = {
            "did-work": {
                "ok": True,
                "this_run": {"completed": 3, "failed": 0},
            },
            "did-nothing": {
                "ok": True,
                "this_run": {"completed": 0, "failed": 0},
            },
            "failed": {
                "ok": False,
                "this_run": {"completed": 0, "failed": 1},
            },
        }
        write_reporter(self.root / "report.py", self.summaries)

    def config(self, *, failure_field: bool = True) -> dict:
        section: dict = {
            "discriminator_fields": ["ok", "this_run"],
            "states": [
                {
                    "name": "completed-work",
                    "outcome": "did_work",
                    "command": [PYTHON, "report.py", "did-work"],
                },
                {
                    "name": "empty-pass",
                    "outcome": "did_nothing",
                    "command": [PYTHON, "report.py", "did-nothing"],
                },
                {
                    "name": "case-failure",
                    "outcome": "failed",
                    "command": [PYTHON, "report.py", "failed"],
                },
            ]
        }
        if failure_field:
            section.update({"failure_field": "ok", "failure_value": False})
        return {"version": 1, "report_discrimination": section}

    def test_distinct_summaries_and_explicit_failure_field_pass(self) -> None:
        result = check_report_discrimination(self.root, self.config())

        self.assertEqual(result.status, "pass", result.details)
        self.assertEqual(result.details["collisions"], [])
        self.assertEqual(result.details["failure_signal"]["mode"], "field")
        self.assertEqual(result.details["declared_states"], 3)

    def test_incidental_timestamps_cannot_fake_discrimination(self) -> None:
        summaries = {
            "did-work": {"ok": True, "this_run": {}, "lastRunAt": "01:00"},
            "did-nothing": {"ok": True, "this_run": {}, "lastRunAt": "01:01"},
            "failed": {"ok": False, "this_run": {}, "lastRunAt": "01:02"},
        }
        write_reporter(self.root / "report.py", summaries)

        result = check_report_discrimination(self.root, self.config())

        self.assertEqual(result.status, "fail")
        self.assertEqual(
            result.details["collisions"],
            [["completed-work", "empty-pass"]],
        )

    def test_did_work_and_did_nothing_must_not_share_a_summary(self) -> None:
        summaries = dict(self.summaries)
        summaries["did-nothing"] = summaries["did-work"]
        write_reporter(self.root / "report.py", summaries)

        result = check_report_discrimination(self.root, self.config())

        self.assertEqual(result.status, "fail")
        self.assertEqual(
            result.details["collisions"],
            [["completed-work", "empty-pass"]],
        )

    def test_failure_must_not_reuse_the_success_field_value(self) -> None:
        summaries = dict(self.summaries)
        summaries["failed"] = {
            "ok": True,
            "this_run": {"completed": 0, "failed": 1},
        }
        write_reporter(self.root / "report.py", summaries)

        result = check_report_discrimination(self.root, self.config())

        self.assertEqual(result.status, "fail")
        self.assertIn("must report ok=False", result.details["invalid"][0])

    def test_failure_field_must_be_part_of_the_declared_projection(self) -> None:
        config = self.config()
        config["report_discrimination"]["discriminator_fields"] = ["this_run"]

        result = check_report_discrimination(self.root, config)

        self.assertEqual(result.status, "fail")
        self.assertIn("failure_field must also appear", result.reason)

    def test_every_state_must_include_each_declared_field(self) -> None:
        summaries = dict(self.summaries)
        summaries["did-nothing"] = {"ok": True}
        write_reporter(self.root / "report.py", summaries)

        result = check_report_discrimination(self.root, self.config())

        self.assertEqual(result.status, "fail")
        self.assertIn("missing declared discriminator field", result.details["invalid"][0])

    def test_nonzero_failure_exit_is_sufficient_without_a_field(self) -> None:
        write_reporter(self.root / "report.py", self.summaries, failed_exit=1)

        result = check_report_discrimination(
            self.root, self.config(failure_field=False)
        )

        self.assertEqual(result.status, "pass", result.details)
        self.assertEqual(result.details["failure_signal"], {"mode": "exit-code"})

    def test_zero_exit_failure_without_a_field_fails(self) -> None:
        result = check_report_discrimination(
            self.root, self.config(failure_field=False)
        )

        self.assertEqual(result.status, "fail")
        self.assertIn("exited zero", result.details["invalid"][0])

    def test_commands_must_emit_one_json_object(self) -> None:
        (self.root / "report.py").write_text("print('not json')\n", encoding="utf-8")

        result = check_report_discrimination(self.root, self.config())

        self.assertEqual(result.status, "fail")
        self.assertEqual(len(result.details["invalid"]), 3)
        self.assertIn("one JSON object", result.details["invalid"][0])

    def test_all_three_outcome_classes_are_required(self) -> None:
        config = self.config()
        config["report_discrimination"]["states"] = config[
            "report_discrimination"
        ]["states"][:2]

        result = check_report_discrimination(self.root, config)

        self.assertEqual(result.status, "fail")
        self.assertIn("at least did_work", result.reason)

    def test_absent_section_is_explicitly_vacuous(self) -> None:
        result = check_report_discrimination(self.root, {"version": 1})

        self.assertEqual(result.status, "pass")
        self.assertTrue(result.details["vacuous"])
        self.assertIn("establishes nothing", result.reason)

    def test_assurance_bound_counts_declared_report_states(self) -> None:
        bound = _assurance_bound(self.config())

        self.assertEqual(
            bound["report_discrimination"],
            {
                "declared_states": 3,
                "declared_outcomes": ["did_nothing", "did_work", "failed"],
                "declared_fields": ["ok", "this_run"],
            },
        )
        self.assertIn("truthfully reproduce", bound["does_not_establish"])


if __name__ == "__main__":
    unittest.main()
