# Self-Hosted Epistemic CI Advisor GitHub App

The self-hosted advisor removes discovery friction without taking repository
write authority. The adopting organization creates and owns the GitHub App,
credentials, container, storage, and logs. It reacts to `/epistemic-ci setup`,
checks that the sender is a repository writer, reads a bounded set of repository
metadata and text files, and opens a setup issue containing candidate mechanics
and the human-confirmation questions.

It does not execute repository code, create branches, open pull requests, read
Actions secrets, change settings, or merge. Repository-owned agents and GitHub
Actions perform those steps under the repository's existing authority.

Self-hosting is the default and currently supported deployment. Repository
material remains inside the adopter's infrastructure and does not pass through
a Silentpartnercoding-operated service. The same container could be operated as
an explicitly opt-in managed service in the future, but no managed service is
currently running or required.

## GitHub App registration

The adopting organization creates its own GitHub App with:

- **Webhook URL:** `https://<host>/github/webhook`
- **Webhook secret:** a new random secret stored only in GitHub and the host
- **Repository permissions:**
  - Contents: **Read-only**
  - Issues: **Read and write**
  - Metadata: **Read-only** (GitHub supplies this automatically)
- **Subscribe to events:** Issue comment
- **Installation:** recommend selected repositories rather than all repositories

Do not grant Pull requests, Actions, Administration, Secrets, Workflows, Checks,
Deployments, or Contents write permission to this version.

This follows GitHub's
[least-privilege guidance](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app).
The sender authorization check uses GitHub's
[repository permission endpoint](https://docs.github.com/en/rest/collaborators/collaborators#get-repository-permissions-for-a-user),
which is available to an installation token with Metadata read permission. The
App's only subscribed event is GitHub's
[`issue_comment` webhook](https://docs.github.com/en/webhooks/webhook-events-and-payloads#issue_comment).

Generate a private key after registration. Store it as a host secret or mounted
secret file; never commit it.

## Deployment

The service is provider-neutral and ships as a Docker container:

```bash
docker build -f deploy/github-app/Dockerfile -t epistemic-ci-advisor .
docker run --rm -p 8080:8080 \
  --env-file deploy/github-app/.env \
  -v epistemic-ci-data:/data \
  -v /absolute/path/app-private-key.pem:/run/secrets/github-app-private-key.pem:ro \
  epistemic-ci-advisor
```

The host must provide public HTTPS and persistent `/data` storage. The SQLite
delivery ledger prevents replayed webhook deliveries from creating duplicate
setup issues. Use one service replica with the bundled SQLite ledger. A
multi-replica deployment requires replacing it with a shared transactional
store implementing the same unique-delivery claim.

Health check: `GET /healthz`.

## Request flow

1. GitHub signs the webhook body with HMAC-SHA256.
2. The service verifies the signature and claims the delivery identifier once.
3. It accepts only a newly created issue comment whose first line is exactly
   `/epistemic-ci setup`.
4. It requests a short-lived installation token.
5. It verifies that the sender has `write`, `maintain`, or `admin` permission.
6. It reads the default-branch tree and fetches only workflows and recognized
   manifests needed for discovery. Candidate artifact discovery uses filenames,
   not artifact contents.
7. A temporary snapshot is deleted immediately after discovery.
8. The service opens a setup issue and links it from the triggering thread.

## Security and privacy boundary

- Maximum webhook size: 2 MB.
- Maximum repository tree: 100,000 entries.
- Maximum fetched text blob: 1 MB; at most 50 text files are fetched.
- Paths are rejected if absolute, parent-traversing, NUL-containing, or excessive.
- Repository code is never executed by the hosted service.
- Raw webhook bodies and repository contents are not logged or retained.
- Error comments are deliberately generic.
- A discovery report is a proposal, not evidence that its candidates are correct.
- GitHub identity and collaborator permission establish who issued the command;
  they do not establish scientific truth or verifier independence.

## Local development

Install the optional service dependencies and start the app:

```bash
python -m pip install -e '.[github-app]'
uvicorn epistemic_ci.github_app:app --host 127.0.0.1 --port 8080
```

Use a webhook relay only with a dedicated development App and test repository.
Do not expose production credentials to a local tunnel.
