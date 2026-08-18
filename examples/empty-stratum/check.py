from __future__ import annotations
import json, sys
from pathlib import Path
p = Path("results/result.json")
if not p.is_file():
    sys.exit(1)
sys.exit(0 if json.loads(p.read_text(encoding="utf-8"))
         == {"population": ["alpha", "beta"], "verdict": "PASS"} else 1)
