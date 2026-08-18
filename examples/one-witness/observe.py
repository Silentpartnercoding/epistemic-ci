from __future__ import annotations
import hashlib, json
from generate import generate


def digest(b: bytes) -> str:
    return f"sha256:{hashlib.sha256(b).hexdigest()}"


out = generate()
result = json.loads(out.read_text(encoding="utf-8"))
pop = json.dumps(result["population"], sort_keys=True, separators=(",", ":")).encode()
raw = out.read_bytes()
print(json.dumps({
    "schema": "epistemic-ci.observation.v1",
    "run_id": digest(pop + raw),
    "population": {"count": len(result["population"]), "fingerprint": digest(pop)},
    "result": {"fingerprint": digest(raw)},
}, sort_keys=True))
