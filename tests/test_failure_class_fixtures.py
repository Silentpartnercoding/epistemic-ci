"""The three fixtures must each fail exactly one check, and no other.

A fixture that fails several checks demonstrates an incomplete configuration
rather than the defect it is about. These tests pin the discrimination: ordinary
verification is green, seven checks pass, and exactly one refuses.

They also pin the *reason*. A fixture that started failing its target check for
an unrelated cause would still pass a count-only assertion.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

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


@pytest.mark.parametrize("fixture,target,phrase", CASES)
def test_fixture_fails_exactly_its_target_check(fixture, target, phrase):
    result = _run_gate(fixture)
    failing = {c["name"]: c for c in result["checks"] if c["status"] != "pass"}
    assert list(failing) == [target], (
        f"{fixture} should fail only {target}; failed {sorted(failing)}")
    assert phrase in failing[target]["reason"], (
        f"{fixture} failed {target} for an unexpected reason: {failing[target]['reason']}")
    assert result["status"] == "fail"


@pytest.mark.parametrize("fixture,target,phrase", CASES)
def test_ordinary_verification_is_green(fixture, target, phrase):
    """The whole point: ordinary CI passes on every one of these."""
    proc = subprocess.run(
        [sys.executable, "verify.py"],
        cwd=ROOT / "examples" / fixture, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"{fixture}: ordinary verification should pass\n{proc.stdout}{proc.stderr}"
    assert "PASS" in proc.stdout


def test_the_three_targets_are_distinct():
    """Three fixtures, three different checks. If two collapsed onto one check
    the set would demonstrate less than it claims."""
    assert len({target for _, target, _ in CASES}) == 3
