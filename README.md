# Epistemic CI

Epistemic CI is a small, vendor-neutral meta-validation gate for computational
research. It tests the verification path before anyone treats a green check as
evidence.

In plain language: it is a test for the tests.

## The eight v0 checks

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
5. **Pinned Input Binding** corrupts the workspace copy of every declared pinned
   input. The result must not move. A runner that claims its results came from
   specific bytes, but reads the working tree, fails here.
6. **Control Discrimination** requires every declared control to fire on at least
   one input and *not* fire on at least one. A control that fires on everything
   measures the population, not the checker.
7. **Evidential Independence** requires every pair of tests cited as separate
   evidence to be separated by at least one declared mutation. Identical fire
   patterns mean the configuration cannot tell them apart.

Checks 6 and 7 are both questions about the shape of one outcome matrix — every
declared test run against the clean tree and each mutation. Check 6 asks whether
a row varies at all; check 7 asks whether two rows are identical. Vacuous Test
asks only *does a defect cause failure?*, and is blind to both: a control that
fires on everything still fails when a defect is planted, and an implied test
still fails when the implying one does. **That correlation is the defect, and it
reads as health.**

8. **Effect Reachability** requires every stratum the endpoint depends on to
   contain instances. A population with 208 searched and 0 not-searched is
   positive, fingerprinted, and structurally unable to move the endpoint.

Check 8 is the only one that interrogates the **population** rather than the
verification path, and it is the only failure no amount of checking the checker
can find: planting a defect *does* make verification fail, and the verifier is
sound. The corpus simply contains no instances of the phenomenon the endpoint
measures. It uses **strata rather than one count**, because a single positive
count passes the case it exists to catch — 208 is greater than zero.

Check 7 does **not** decide implication, which is undecidable. It reports that no
declared mutation separates two tests, which is a statement about the
configuration rather than about the tests. Two genuinely independent tests can
coincide on a small mutation set, and the result says so instead of asserting
redundancy. The remedy is a mutation that separates them, or an admission that
they are one piece of evidence.

Check 5 has the opposite polarity to the others, and that is the point. Checks
1, 2 and 4 establish that verification is *sensitive* to corruption. Check 5
establishes that it is *insensitive* where it claims to be pinned — because
sensitivity in the wrong place is itself a defect, and a silent one: every
recorded digest still matches, since the digest is taken of the same working-tree
copy that was executed.

The two are reconciled by partitioning inputs rather than ranking the checks:

| kind | read from | corrupt the workspace copy |
|---|---|---|
| live | the workspace, at run time | verification must **fail** (check 1) |
| pinned | an immutable reference | the result must **not move** (check 5) |

An input cannot be both. A path declared as a `vacuous_test` mutation target
*and* as a pin is a contradiction in the configuration and is rejected, because
either answer would be wrong for one of the two checks.

**What check 5 does and does not establish.** Insensitivity is checked
generically and always. *Sensitivity* — that corrupting what the pin resolves to
makes the run fail — depends on the pin mechanism, which this tool cannot know: a
pin may be a commit, a digest, an archive or a registry reference. Where the
configuration supplies `tamper_command`, sensitivity is checked. Where it does
not, it is reported as **not established** for that pin rather than assumed, and
the count is carried in the assurance bound. Pins are counted separately from
mutations, so they cannot inflate the number a reader judges a pass by.

One known limitation: `.git` is excluded from the isolated workspace, so a pin
resolved by `git show` inside the workspace cannot be exercised by this check.
Pins that resolve outside the workspace, or via a `tamper_command`, can.

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

## See an ordinary green check fail the test-for-the-tests

[`examples/vacuous-green`](examples/vacuous-green) is an intentionally broken,
synthetic comparison. Its ordinary verifier returns success while ignoring the
declared source. Epistemic CI changes that source in an isolated workspace,
sees the ordinary verifier remain green, and identifies the planted defect as a
survivor.

```bash
python3 examples/vacuous-green/ordinary_ci.py
python3 -m unittest tests.test_vacuous_green_demo -v
```

The dedicated `vacuous-green-demo` GitHub workflow publishes both observations:
ordinary CI stays green, and Epistemic CI catches why that green check is not
evidence of source-sensitive verification.

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
