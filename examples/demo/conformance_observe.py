from __future__ import annotations

import json
import sys
from pathlib import Path


vector = json.loads(
    Path("conformance-causality-001.json").read_text(encoding="utf-8")
)
observed = dict(vector["expected"])
if sys.argv[1] == "short-circuit-mutant":
    observed["property_reached"] = False
    observed["stop_reason"] = "UNSUPPORTED_VERSION"

print(json.dumps(observed, sort_keys=True))
