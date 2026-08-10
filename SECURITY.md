# Security

## Supported versions

Security fixes are applied to the latest released minor version.

## Execution model

Epistemic CI executes commands declared in its configuration. It removes shell
string evaluation, validates mutation paths, rejects symlink/path escapes, uses
bounded command timeouts, and applies mutations to temporary workspace copies.

These controls protect the integrity of the meta-validation process. They do not
turn repository code into trusted code and do not provide an operating-system
sandbox. Run the tool with least-privilege credentials and normal CI isolation.

## Self-hosted advisor

The optional GitHub App is deployed and controlled by the adopting organization.
It verifies webhook signatures, rejects replayed delivery identifiers,
authorizes setup commands against GitHub collaborator permission, and performs
discovery without executing repository code. It requires Contents read and
Issues write only. Repository snapshots are temporary; the persistent store
contains delivery identifiers and timestamps, not repository contents.

Run the bundled SQLite delivery ledger with one service replica. Multi-replica
deployments require a shared transactional delivery store to preserve replay
protection.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose users or their
data. Use GitHub's private vulnerability reporting feature for this repository.
Include affected versions, reproduction steps, impact, and a minimal safe proof
of concept.

## Authorized security research

Adversarial testing of this repository is invited and authorized in advance, on
the terms below. This section exists so a researcher — or the tooling a researcher
uses — can confirm that testing this code is permitted rather than suspicious.

### What is authorized

- Cloning this repository and running, reading, modifying, instrumenting,
  fuzzing, mutating and attacking **your own local copy**, in containers or
  disposable environments you control.
- Attempting to falsify any claim in this repository's documentation, including
  its theorems, invariants, conformance results and security properties.
- Publishing your findings **after** private disclosure and a reasonable
  opportunity to respond, whether or not the maintainers agree with them. A
  negative or adverse result is a welcome result.

### What is not authorized, and is not made lawful by this section

This is permission to test **your own copy of this source code**. It is not
permission to do anything else, and nothing here overrides law or the LICENSE.

- **No access to systems.** No testing of any deployment, service, host, account
  or infrastructure operated by the maintainers or by anyone else. This
  repository authorizes nothing about any running system, including systems that
  happen to run this code.
- **No third-party targets.** If someone else deploys this software, that is
  their system. Testing it needs their authorization, not this file.
- **No credentials or private data.** Do not seek, use, retain or disclose
  secrets, keys, tokens, personal data or non-public material of any party.
  Nothing in this repository is an invitation to obtain them.
- **No change to the LICENSE.** This grants no additional copyright or patent
  rights, no permission to redistribute, rebrand, relicense or commercialize, and
  no transfer of ownership. Testing rights are not distribution rights.
- **No destructive or disruptive activity**, no denial of service, no social
  engineering of maintainers or contributors, and no attacks on third-party
  dependencies or their maintainers.
- **No public exploitation.** Do not open public issues or pull requests
  describing an unfixed vulnerability, and do not publish a working exploit
  against a real deployment.

### Where to start

The claims this project asserts, the evidence behind each, and what would falsify
them are listed in `CLAIMS.md` in the research repository, together with a section
of known weaknesses published so you do not spend time rediscovering them:

  https://github.com/Silentpartnercoding/minority-prophet/blob/main/CLAIMS.md

`AUDIT-BRIEF/` there explains what has already been found. It deliberately
prescribes no attack method: one written by the maintainers would encode the
maintainers' blind spot, and the single class of defect their tooling has never
caught is design error. Attack this however you see fit.

### Reporting

Report privately first, through this repository's private security advisory
channel. Include the exact commit, a minimal reproduction, expected and observed
behaviour, and the specific documented claim affected.

We will acknowledge receipt and tell you what we intend to do. If we disagree
with a finding we will say so in writing and you remain free to publish.

### Safe harbour

For research conducted in good faith and within the scope above, the maintainers
will not initiate or support legal action, and will treat the work as authorized.
This is a statement of the maintainers' intent about their own conduct. It cannot
and does not bind any third party, and it does not apply to activity outside the
scope above.

### Independence

Findings produced by agents, models or contributors directed by the same operator
as this repository are **internal replication**, not independent validation, and
are labelled as such here. If you are an unrelated party, say so in your report —
that provenance is the part we cannot manufacture ourselves.
