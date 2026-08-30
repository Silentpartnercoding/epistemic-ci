from __future__ import annotations

import json
from pathlib import Path
import sys


path = Path("results/result.json")
valid = path.is_file() and json.loads(path.read_text(encoding="utf-8")) == {
    "verdict": "PASS"
}
sys.exit(0 if valid else 1)
