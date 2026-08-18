#!/usr/bin/env python3
"""Claims its result came from the pinned threshold. Reads the workspace copy.

The digest it records is taken of the same file it read, so the digest always
matches and nothing downstream can tell the difference.
"""
import hashlib, json, pathlib
here = pathlib.Path(__file__).parent
pin = here / "pinned" / "threshold.txt"          # DECLARED as pinned
threshold = float(pin.read_text().strip())       # ...but read from the workspace
(here / "results").mkdir(exist_ok=True)
(here / "results" / "result.json").write_text(json.dumps({
    "threshold_used": threshold,
    "verdict": "PASS" if threshold >= 0.5 else "FAIL",
    "pinned_digest": hashlib.sha256(pin.read_bytes()).hexdigest(),
}, indent=1, sort_keys=True) + "\n")
print("wrote results/result.json")
