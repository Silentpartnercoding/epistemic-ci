"""The fifth check: a declared-pinned input must be read from its pin.

Motivated by a real defect, not by symmetry. Minority Prophet's
canonical-capability-runner.py pinned two files at a commit, recorded their
hashes in a published result, and then hashed and EXECUTED the working-tree
copies. It agreed with the pin exactly as long as nobody edited those files.
"""

import json
import subprocess
from pathlib import Path

import pytest

from epistemic_ci.core import check_pinned_input_binding, run_all


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_project(tmp_path: Path, *, pinned: bool) -> Path:
    """A runner that either reads the pin (correct) or the workspace (the bug).

    The pin is modelled as a store the working copy does not overlap, which is
    what a git commit object actually is. `.git` itself is excluded from the
    isolated workspace, so a literal `git show` pin cannot be exercised here --
    a real limitation of this check, recorded in the README.
    """
    root = tmp_path / "project"
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


def test_a_runner_that_reads_the_pin_passes(tmp_path):
    root = make_project(tmp_path, pinned=True)
    result = check_pinned_input_binding(root, CONFIG)
    assert result.status == "pass", result.details
    assert result.details["held"] == ["source-pinned-at-commit"]


def test_a_runner_that_reads_the_workspace_is_caught(tmp_path):
    """The exact defect. Every recorded digest would still match, because the
    digest is taken of the same copy that was executed."""
    root = make_project(tmp_path, pinned=False)
    result = check_pinned_input_binding(root, CONFIG)
    assert result.status == "fail"
    assert any("live, not pinned" in entry for entry in result.details["moved"])


def test_declaring_a_path_as_both_live_and_pinned_is_rejected(tmp_path):
    """THE RECONCILIATION. vacuous-test requires corruption to FAIL the run;
    this check requires it to leave the result UNCHANGED. A path declared to
    both is a contradiction, and is rejected rather than silently resolved."""
    root = make_project(tmp_path, pinned=True)
    config = dict(CONFIG)
    config["vacuous_test"] = {
        "verify_command": ["true"],
        "timeout_seconds": 60,
        "mutations": [
            {"name": "same-file", "path": "source.txt",
             "search": "CANONICAL", "replace": "X"}
        ],
    }
    result = check_pinned_input_binding(root, config)
    assert result.status == "fail"
    assert "never both" in result.reason or "never both" in str(result.details)


def test_sensitivity_is_reported_unestablished_rather_than_assumed(tmp_path):
    """Insensitivity is generic. Sensitivity depends on the pin mechanism, so
    without a tamper_command it is reported as not established, never assumed."""
    root = make_project(tmp_path, pinned=True)
    result = check_pinned_input_binding(root, CONFIG)
    assert result.details["sensitivity_not_established"] == ["source-pinned-at-commit"]
    assert result.details["sensitivity_established"] == []


def test_absent_section_does_not_break_existing_configs_but_says_so(tmp_path):
    root = make_project(tmp_path, pinned=True)
    result = check_pinned_input_binding(root, {"version": 1})
    assert result.status == "pass"
    assert result.details["vacuous"] is True
    assert "establishes nothing" in result.reason


def test_assurance_bound_carries_the_pin_counts(tmp_path):
    root = make_project(tmp_path, pinned=True)
    report = run_all(root, CONFIG)
    bound = json.loads(json.dumps(report["assurance_bound"]))
    assert bound["pinned_inputs"]["declared"] == 1
    assert bound["pinned_inputs"]["with_sensitivity_check"] == 0
    # Pins must not inflate the mutation total a reader judges a pass by.
    assert "pinned_inputs_declared" not in bound["declared_mutations"]
