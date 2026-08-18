#!/usr/bin/env python3
"""Ordinary verification. It is SOUND: plant a defect and it fails."""
import pathlib, sys
corpus = sorted(pathlib.Path(__file__).parent.joinpath("corpus").glob("*.txt"))
if not corpus:
    print("FAIL: empty corpus"); sys.exit(1)
for p in corpus:
    body = p.read_text()
    if "status:" not in body:
        print(f"FAIL: {p.name} has no status"); sys.exit(1)
print(f"PASS: {len(corpus)} documents verified")
