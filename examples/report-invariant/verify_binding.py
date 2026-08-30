from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


try:
    receipt = json.loads(Path("results/binding.json").read_text(encoding="utf-8"))
    artifacts = receipt["artifacts"]
    artifact = artifacts[0]
    path = Path(artifact["path"])
    expected = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    valid = (
        receipt["schema"] == "epistemic-ci.final-artifact-binding.v1"
        and len(artifacts) == 1
        and artifact["path"] == "results/result.json"
        and artifact["sha256"] == expected
    )
except (KeyError, IndexError, OSError, TypeError, json.JSONDecodeError):
    valid = False

sys.exit(0 if valid else 1)
