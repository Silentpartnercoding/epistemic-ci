#!/usr/bin/env python3
"""Ordinary verification: the recorded digest matches the file. It always will."""
import hashlib, json, pathlib, sys
here = pathlib.Path(__file__).parent
r = json.loads((here / "results" / "result.json").read_text())
actual = hashlib.sha256((here / "pinned" / "threshold.txt").read_bytes()).hexdigest()
if r["pinned_digest"] != actual:
    print("FAIL: digest mismatch"); sys.exit(1)
if "sample" not in (here / "live_input.txt").read_text():
    print("FAIL: live input missing"); sys.exit(1)
print("PASS: digest matches the pinned input")
