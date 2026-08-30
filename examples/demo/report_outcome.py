from __future__ import annotations

import json
import sys


state = sys.argv[1]
summaries = {
    "did-work": {
        "ok": True,
        "this_run": {"considered": 2, "completed": 2, "failed": 0},
    },
    "did-nothing": {
        "ok": True,
        "this_run": {"considered": 0, "completed": 0, "failed": 0},
    },
    "failed": {
        "ok": False,
        "this_run": {"considered": 1, "completed": 0, "failed": 1},
    },
}
print(json.dumps(summaries[state], sort_keys=True))
