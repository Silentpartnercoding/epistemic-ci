from __future__ import annotations
import hashlib, json
from pathlib import Path
from generate import generate
out = generate()
Path("results/binding.json").write_text(json.dumps({
    "schema": "epistemic-ci.final-artifact-binding.v1",
    "run_id": "fixture-run",
    "artifacts": [{"path": "results/result.json",
                   "sha256": f"sha256:{hashlib.sha256(out.read_bytes()).hexdigest()}"}],
}, sort_keys=True) + "\n", encoding="utf-8")
