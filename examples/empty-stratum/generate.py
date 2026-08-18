"""Sound plumbing, shared by the three fixtures.

These four sections exist so each fixture fails on exactly ONE check. A fixture
that failed four checks would demonstrate an incomplete configuration, not the
defect it is about.
"""
from __future__ import annotations
import json
from pathlib import Path


def generate() -> Path:
    verdict = Path("source.txt").read_text(encoding="utf-8").strip()
    out = Path("results/result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"population": ["alpha", "beta"], "verdict": verdict},
                              sort_keys=True) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    generate()
