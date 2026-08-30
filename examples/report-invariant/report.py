"""Broken by construction: every outcome emits the same green summary."""

from __future__ import annotations

import json


print(json.dumps({"ok": True, "cases": 23, "observations": 994}, sort_keys=True))
