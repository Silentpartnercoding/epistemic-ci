from __future__ import annotations

import hashlib
import json
from pathlib import Path

from generate import generate


output = generate()
receipt = {
    "schema": "epistemic-ci.final-artifact-binding.v1",
    "run_id": "demo-run",
    "artifacts": [
        {
            "path": "results/result.json",
            "sha256": f"sha256:{hashlib.sha256(output.read_bytes()).hexdigest()}",
        }
    ],
}
Path("results/binding.json").write_text(
    json.dumps(receipt, sort_keys=True) + "\n",
    encoding="utf-8",
)
