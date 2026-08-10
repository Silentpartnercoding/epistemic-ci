# Epistemic CI

Epistemic CI is a small, vendor-neutral meta-validation gate for computational
research. It tests the verification path before anyone treats a green check as
evidence.

In plain language: it is a test for the tests.

## The four v0 checks

1. **Vacuous Test** plants every declared source or input defect in a fresh
   workspace. Every defect must make verification fail.
2. **Executable Pass Condition** generates fresh output, confirms the declared
   checker accepts it, then corrupts every declared generated-output target.
   Every corruption must make the checker fail.
3. **Observation Surface** requires one machine-readable observation that binds
   a positive population count, population fingerprint, and result fingerprint
   to one run identifier.
4. **Final Artifact Binding** requires a detached receipt that names and hashes
   every declared final artifact. The configured verifier must reject each
   altered artifact and a tampered receipt.

All four checks fail closed. A surviving, invalid, missing, escaped, or timed-out
test makes the complete run fail.

**What a passing run is bounded by.** Checks 1 and 2 plant the defects the
configuration *declares*. A pass establishes that the verification path rejects
those defects and nothing more: a verifier whose author declared only defects it
happens to catch will pass. That limit cannot be closed by a stricter check —
deciding whether a declared mutation set is representative requires knowing which
defects matter, which is the thing under study. So every result carries an
`assurance_bound` object stating the declared count and what the run does not
establish, in machine-readable form, so a summary or a badge cannot drop it.

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

## Agent-assisted repository pairing

An agent can perform mechanical discovery without being allowed to invent what
the repository's evidence means:

```bash
epistemic-ci init --root . --output epistemic-ci-onboarding.json
```

The report lists candidate verification commands, workflow files, and likely
artifacts, then asks three plain-language questions:

1. Which final files or results do people actually trust?
2. Which planted mistakes must make verification fail?
3. What exact population or evidence produced the result?

The repository owner may answer through an agent. The agent records the
confirmed answers using `epistemic-ci.onboarding-answers.v1`, implements the
smallest project-specific adapters, and validates the proposed configuration:

```bash
epistemic-ci init \
  --root . \
  --answers .epistemic-ci-answers.json \
  --config .epistemic-ci.json \
  --output epistemic-ci-onboarding.json \
  --force
```

Only a report with `status: ready_for_human_review` has complete human answers
and a candidate configuration that passes all four deterministic checks. This
status is not self-approval: the agent opens a reviewable pull request, and the
owner or separately controlled reviewer decides whether the declarations match
the intended claim.

See [EPISTEMIC-CI-SETUP.md](EPISTEMIC-CI-SETUP.md) for the agent execution
contract and [examples/onboarding-answers.json](examples/onboarding-answers.json)
for the answers format.

## Self-Hosted GitHub Advisor

The optional self-hosted advisor turns repository discovery into a GitHub-native
command. The adopting organization creates and owns its GitHub App, credentials,
container, storage, and logs. An authorized maintainer comments
`/epistemic-ci setup`; the app performs read-only discovery and opens a setup
issue for human confirmation or agent handoff.

The advisor deliberately requests **Contents read** and **Issues write** only.
It does not request repository contents write, Pull requests, Actions,
Administration, Secrets, Workflows, Checks, deployment, or merge authority. It
never executes repository code. The repository owner or their existing agent
creates the draft configuration pull request, and the repository's own GitHub
Actions execute Epistemic CI.

Self-hosting is the default deployment model. Repository material is processed
inside the adopter's infrastructure and does not pass through a
Silentpartnercoding-operated service. The same container could support a future
managed offering, but no managed service is currently operated or required.

See [docs/GITHUB-APP.md](docs/GITHUB-APP.md) for registration, deployment,
permissions, and the security model.

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
  },
  "final_artifact_binding": {
    "prepare_command": ["python3", "bind.py"],
    "verify_command": ["python3", "verify_binding.py"],
    "artifact_paths": ["results/result.json"],
    "receipt_path": "results/binding.json"
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

## Final-artifact binding contract

The preparation command must finalize the declared artifacts and then write one
detached JSON receipt. The receipt must remain outside `artifact_paths`; a file
cannot safely contain its own digest.

```json
{
  "schema": "epistemic-ci.final-artifact-binding.v1",
  "run_id": "run-2026-08-09",
  "artifacts": [
    {
      "path": "results/result.json",
      "sha256": "sha256:<64 lowercase hex characters>"
    }
  ]
}
```

Receipt entries must exactly match every file selected by `artifact_paths`, in
sorted repository-relative path order. Epistemic CI independently checks those
digests, then proves the configured verifier rejects each altered artifact and
a tampered receipt.

This avoids a self-referential commit certificate. If a receipt must bind a Git
commit, store it outside that commit (for example as a CI attestation), or bind a
defined tree that excludes the receipt. Epistemic CI does not prescribe the
storage system; it tests the configured artifact-consumer boundary.

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
