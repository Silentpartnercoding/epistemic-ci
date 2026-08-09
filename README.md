# Epistemic CI

Epistemic CI is a small, vendor-neutral meta-validation gate for computational
research. It tests the verification path before anyone treats a green check as
evidence.

In plain language: it is a test for the tests.

## The three v0 checks

1. **Vacuous Test** plants every declared source or input defect in a fresh
   workspace. Every defect must make verification fail.
2. **Executable Pass Condition** generates fresh output, confirms the declared
   checker accepts it, then corrupts every declared generated-output target.
   Every corruption must make the checker fail.
3. **Observation Surface** requires one machine-readable observation that binds
   a positive population count, population fingerprint, and result fingerprint
   to one run identifier.

All three checks fail closed. A surviving, invalid, missing, escaped, or timed-out
test makes the complete run fail.

## What it does not prove

Epistemic CI does **not** certify that a scientific claim is true, that a sample
is representative, that two sources are independent, or that an observation
command is honest. It establishes narrower facts about the configured
verification path. Those facts are useful, but they are not permission,
authority, peer review, or scientific correctness.

## Install and run

Requires Python 3.10 or newer.

From a checkout:

```bash
python3 -m pip install -e .
epistemic-ci run --config .epistemic-ci.json
```

To try the included demonstration:

```bash
epistemic-ci run \
  --root examples/demo \
  --config .epistemic-ci.json \
  --output epistemic-ci-result.json
```

## Configuration

Commands are JSON argument arrays, not shell strings. This avoids implicit shell
expansion and quoting ambiguity.

```json
{
  "version": 1,
  "vacuous_test": {
    "verify_command": ["python3", "verify.py"],
    "mutations": [
      {
        "name": "flip-source-verdict",
        "path": "fixture.txt",
        "search": "PASS",
        "replace": "FAIL"
      }
    ]
  },
  "executable_pass_condition": {
    "prepare_command": ["python3", "generate.py"],
    "check_command": ["python3", "check.py"],
    "generated_paths": ["results/result.json"],
    "mutations": [
      {
        "name": "corrupt-generated-verdict",
        "path": "results/result.json",
        "search": "\"verdict\": \"PASS\"",
        "replace": "\"verdict\": \"FAIL\""
      }
    ]
  },
  "observation_surface": {
    "command": ["python3", "observe.py"]
  }
}
```

Each mutation is applied in a separate copied workspace. Mutation paths must
resolve to UTF-8 regular files inside that workspace, and the search text must
match exactly once. The executable-pass mutations must target files selected by
`generated_paths`.

Each section accepts an optional `timeout_seconds` from 1 to 3600. The default is
120 seconds. `workspace_exclude` may add copy-exclusion patterns when a repository
contains large local artifacts.

## Observation contract

The observation command must print one JSON object:

```json
{
  "schema": "epistemic-ci.observation.v1",
  "run_id": "run-2026-08-09",
  "population": {
    "count": 42,
    "fingerprint": "sha256:<64 lowercase hex characters>"
  },
  "result": {
    "fingerprint": "sha256:<64 lowercase hex characters>"
  }
}
```

Epistemic CI validates the structure and adds a canonical fingerprint over the
observation. The producing command remains responsible for truthfully counting
and fingerprinting the population it actually checked.

## GitHub Action

```yaml
- uses: Silentpartnercoding/epistemic-ci@v0
  with:
    root: .
    config: .epistemic-ci.json
```

Pin third-party Actions to a full commit SHA in higher-assurance environments.
This repository pins the Actions used by its own CI.

## Execution boundary

Epistemic CI executes commands declared by the repository. Use it only on code
you are prepared to execute in the current CI environment. It isolates file
mutations in copied workspaces; it is not an operating-system sandbox and does
not make untrusted code safe. Do not use `pull_request_target` to execute
untrusted pull-request code with privileged credentials.

See [SECURITY.md](SECURITY.md) for the security model and reporting guidance.

## License

Apache License 2.0.
