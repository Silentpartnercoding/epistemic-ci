from __future__ import annotations

from generate import generate
import json
import sys


output = generate()
result = json.loads(output.read_text(encoding="utf-8"))
sys.exit(
    0
    if output.is_file()
    and result == {"population": ["alpha", "beta"], "verdict": "PASS"}
    else 1
)
