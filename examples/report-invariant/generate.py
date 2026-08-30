from __future__ import annotations

import json
from pathlib import Path


def generate() -> Path:
    output = Path("results/result.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    verdict = Path("fixture.txt").read_text(encoding="utf-8").strip()
    output.write_text(
        json.dumps({"verdict": verdict}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


if __name__ == "__main__":
    generate()
