from __future__ import annotations

import json
from pathlib import Path
import sys


path = Path("results/result.json")
if not path.is_file():
    sys.exit(1)
result = json.loads(path.read_text(encoding="utf-8"))
sys.exit(0 if result == {"population": ["alpha", "beta"], "verdict": "PASS"} else 1)
