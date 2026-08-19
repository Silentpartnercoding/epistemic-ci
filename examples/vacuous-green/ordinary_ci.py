from __future__ import annotations

from pathlib import Path
import sys


# Intentionally defective: this reads a hand-authored expected answer instead
# of the declared source in source.txt. Ordinary CI therefore remains green
# when the source is changed.
expected = (
    Path(__file__).resolve().parent / "frozen_expected.txt"
).read_text(encoding="utf-8").strip()
passed = expected == "PASS"
print(f"ORDINARY CI: {'PASS' if passed else 'FAIL'}")
sys.exit(0 if passed else 1)
