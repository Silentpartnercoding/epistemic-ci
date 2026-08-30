from __future__ import annotations

from pathlib import Path
import sys


valid = Path("fixture.txt").read_text(encoding="utf-8").strip() == "PASS"
print("PASS: source verified" if valid else "FAIL: source verdict changed")
sys.exit(0 if valid else 1)
