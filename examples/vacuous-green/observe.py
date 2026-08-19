from __future__ import annotations

import hashlib
import json

from generate import generate


def digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


output = generate()
result = json.loads(output.read_text(encoding="utf-8"))
population = json.dumps(
    result["population"], sort_keys=True, separators=(",", ":")
).encode()
result_bytes = output.read_bytes()
print(
    json.dumps(
        {
            "schema": "epistemic-ci.observation.v1",
            "run_id": digest(population + result_bytes),
            "population": {
                "count": len(result["population"]),
                "fingerprint": digest(population),
            },
            "result": {"fingerprint": digest(result_bytes)},
        },
        sort_keys=True,
    )
)
