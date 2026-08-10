from __future__ import annotations

import json
from pathlib import Path


def generate() -> Path:
    verdict = Path("source.txt").read_text(encoding="utf-8").strip()
    output = Path("results/result.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"population": ["alpha", "beta"], "verdict": verdict}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return output


if __name__ == "__main__":
    generate()
