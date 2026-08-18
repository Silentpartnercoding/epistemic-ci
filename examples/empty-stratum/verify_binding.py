from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
try:
    r = json.loads(Path("results/binding.json").read_text(encoding="utf-8"))
    a = r["artifacts"][0]
    expected = f"sha256:{hashlib.sha256(Path(a['path']).read_bytes()).hexdigest()}"
    ok = (r["schema"] == "epistemic-ci.final-artifact-binding.v1"
          and len(r["artifacts"]) == 1 and a["path"] == "results/result.json"
          and a["sha256"] == expected)
except (KeyError, IndexError, OSError, TypeError, json.JSONDecodeError):
    ok = False
sys.exit(0 if ok else 1)
