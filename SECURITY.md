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
