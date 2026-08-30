from __future__ import annotations

import hashlib
import json

from generate import generate


def digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


output = generate()
population = b"one-report-fixture"
raw = output.read_bytes()
print(
    json.dumps(
        {
            "schema": "epistemic-ci.observation.v1",
            "run_id": digest(population + raw),
            "population": {"count": 1, "fingerprint": digest(population)},
            "result": {"fingerprint": digest(raw)},
        },
        sort_keys=True,
    )
)
