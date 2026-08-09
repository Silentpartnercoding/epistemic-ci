from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import quote

import httpx
import jwt
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .onboarding import ANSWERS_SCHEMA, discover_repository

LOGGER = logging.getLogger("epistemic_ci.github_app")
MAX_WEBHOOK_BYTES = 2_000_000
MAX_TREE_ENTRIES = 100_000
MAX_TEXT_BLOB_BYTES = 1_000_000
DELIVERY_RETENTION_SECONDS = 7 * 24 * 60 * 60
SETUP_COMMAND = "/epistemic-ci setup"
ALLOWED_PERMISSIONS = {"admin", "maintain", "write"}
_REPOSITORY_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}"
)
_LOGIN_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_MANIFEST_PATHS = {
    "Cargo.toml",
    "Makefile",
    "go.mod",
    "noxfile.py",
    "package.json",
    "pyproject.toml",
    "tox.ini",
}
_ARTIFACT_SUFFIXES = {".csv", ".html", ".json", ".pdf", ".sarif", ".xml"}
_ARTIFACT_TERMS = (
    "artifact",
    "coverage",
    "evidence",
    "finding",
    "report",
    "result",
    "summary",
)


class GitHubAppError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    app_id: str
    private_key: str
    webhook_secret: str
    api_url: str = "https://api.github.com"
    delivery_db: str = "/data/epistemic-ci-deliveries.sqlite3"

    @classmethod
    def from_environment(cls) -> Settings:
        app_id = os.environ.get("GITHUB_APP_ID", "").strip()
        webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
        private_key = os.environ.get("GITHUB_PRIVATE_KEY", "").replace("\\n", "\n")
        private_key_path = os.environ.get("GITHUB_PRIVATE_KEY_PATH", "").strip()
        if not private_key and private_key_path:
            try:
                private_key = Path(private_key_path).read_text(encoding="utf-8")
            except OSError as exc:
                raise GitHubAppError("cannot read GITHUB_PRIVATE_KEY_PATH") from exc
        missing = [
            name
            for name, value in (
                ("GITHUB_APP_ID", app_id),
                ("GITHUB_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH", private_key),
                ("GITHUB_WEBHOOK_SECRET", webhook_secret),
            )
            if not value
        ]
        if missing:
            raise GitHubAppError(
                "missing required configuration: " + ", ".join(missing)
            )
        return cls(
            app_id=app_id,
            private_key=private_key,
            webhook_secret=webhook_secret,
            api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip(
                "/"
            ),
            delivery_db=os.environ.get(
                "EPISTEMIC_CI_DELIVERY_DB",
                "/data/epistemic-ci-deliveries.sqlite3",
            ),
        )


class DeliveryStore:
    def __init__(self, path: str) -> None:
        database = Path(path)
        database.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS deliveries "
            "(delivery_id TEXT PRIMARY KEY, received_at INTEGER NOT NULL)"
        )
        self._connection.commit()
        self._lock = threading.Lock()

    def claim(self, delivery_id: str, now: int | None = None) -> bool:
        timestamp = int(time.time()) if now is None else now
        cutoff = timestamp - DELIVERY_RETENTION_SECONDS
        with self._lock:
            self._connection.execute(
                "DELETE FROM deliveries WHERE received_at < ?", (cutoff,)
            )
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO deliveries (delivery_id, received_at) VALUES (?, ?)",
                (delivery_id, timestamp),
            )
            self._connection.commit()
            return cursor.rowcount == 1


def _verify_signature(body: bytes, supplied: str | None, secret: str) -> bool:
    if not supplied or not supplied.startswith("sha256="):
        return False
    expected = (
        "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, supplied)


def _setup_command(body: Any) -> bool:
    if not isinstance(body, str):
        return False
    first_line = body.strip().splitlines()[0].strip().lower() if body.strip() else ""
    return first_line == SETUP_COMMAND


def _valid_setup_payload(payload: dict[str, Any]) -> bool:
    installation_data = payload.get("installation")
    repository_data = payload.get("repository")
    sender_data = payload.get("sender")
    issue_data = payload.get("issue")
    if not all(
        isinstance(item, dict)
        for item in (installation_data, repository_data, sender_data, issue_data)
    ):
        return False
    installation_id = installation_data.get("id")
    repository = repository_data.get("full_name")
    branch = repository_data.get("default_branch") or "main"
    username = sender_data.get("login")
    issue_number = issue_data.get("number")
    return (
        isinstance(installation_id, int)
        and installation_id > 0
        and isinstance(repository, str)
        and _REPOSITORY_PATTERN.fullmatch(repository) is not None
        and isinstance(branch, str)
        and 0 < len(branch) <= 255
        and "\x00" not in branch
        and isinstance(username, str)
        and _LOGIN_PATTERN.fullmatch(username) is not None
        and isinstance(issue_number, int)
        and issue_number > 0
    )


def _safe_repo_path(value: str) -> PurePosixPath | None:
    if not value or len(value) > 1024 or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def _needs_content(path: PurePosixPath) -> bool:
    value = path.as_posix()
    return value in _MANIFEST_PATHS or (
        value.startswith(".github/workflows/") and path.suffix in {".yml", ".yaml"}
    )


def _needs_placeholder(path: PurePosixPath) -> bool:
    value = path.as_posix()
    if _needs_content(path) or value.startswith("tests/"):
        return True
    lowered = path.name.lower()
    return path.suffix.lower() in _ARTIFACT_SUFFIXES and any(
        term in lowered for term in _ARTIFACT_TERMS
    )


class GitHubInstallationClient:
    def __init__(
        self,
        settings: Settings,
        installation_id: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.installation_id = installation_id
        self.transport = transport
        self._token: str | None = None

    def _app_jwt(self) -> str:
        now = int(time.time())
        encoded = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self.settings.app_id},
            self.settings.private_key,
            algorithm="RS256",
        )
        return encoded if isinstance(encoded, str) else encoded.decode("utf-8")

    async def _installation_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient(
            base_url=self.settings.api_url,
            transport=self.transport,
            timeout=15,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._app_jwt()}",
                "X-GitHub-Api-Version": "2026-03-10",
            },
        ) as client:
            response = await client.post(
                f"/app/installations/{self.installation_id}/access_tokens"
            )
        if response.status_code != 201:
            raise GitHubAppError("GitHub installation-token request failed")
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise GitHubAppError("GitHub installation-token response was incomplete")
        self._token = token
        return token

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = await self._installation_token()
        async with httpx.AsyncClient(
            base_url=self.settings.api_url,
            transport=self.transport,
            timeout=20,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2026-03-10",
            },
        ) as client:
            response = await client.request(method, path, **kwargs)
        return response

    async def collaborator_permission(self, repository: str, username: str) -> str:
        owner, name = repository.split("/", 1)
        response = await self.request(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/collaborators/{quote(username)}/permission",
        )
        if response.status_code == 404:
            return "none"
        if response.status_code != 200:
            raise GitHubAppError("GitHub collaborator-permission request failed")
        permission = response.json().get("permission")
        return permission if isinstance(permission, str) else "none"

    async def add_comment(self, repository: str, issue_number: int, body: str) -> None:
        owner, name = repository.split("/", 1)
        response = await self.request(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/issues/{issue_number}/comments",
            json={"body": body},
        )
        if response.status_code != 201:
            raise GitHubAppError("GitHub issue-comment request failed")

    async def create_issue(self, repository: str, title: str, body: str) -> str:
        owner, name = repository.split("/", 1)
        response = await self.request(
            "POST",
            f"/repos/{quote(owner)}/{quote(name)}/issues",
            json={"title": title, "body": body},
        )
        if response.status_code != 201:
            raise GitHubAppError("GitHub setup-issue request failed")
        url = response.json().get("html_url")
        if not isinstance(url, str) or not url:
            raise GitHubAppError("GitHub setup-issue response was incomplete")
        return url

    async def repository_snapshot(
        self,
        repository: str,
        branch: str,
    ) -> tuple[str, dict[str, Any]]:
        owner, name = repository.split("/", 1)
        commit_response = await self.request(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/commits/{quote(branch, safe='')}",
        )
        if commit_response.status_code != 200:
            raise GitHubAppError("GitHub default-branch request failed")
        commit_payload = commit_response.json()
        commit_sha = commit_payload.get("sha")
        tree_sha = commit_payload.get("commit", {}).get("tree", {}).get("sha")
        if not isinstance(commit_sha, str) or not isinstance(tree_sha, str):
            raise GitHubAppError("GitHub default-branch response was incomplete")
        tree_response = await self.request(
            "GET",
            f"/repos/{quote(owner)}/{quote(name)}/git/trees/{quote(tree_sha)}?recursive=1",
        )
        if tree_response.status_code != 200:
            raise GitHubAppError("GitHub repository-tree request failed")
        tree_payload = tree_response.json()
        tree = tree_payload.get("tree")
        if not isinstance(tree, list) or len(tree) > MAX_TREE_ENTRIES:
            raise GitHubAppError(
                "repository tree is missing or exceeds the supported size"
            )
        selected: list[tuple[PurePosixPath, str | None]] = []
        tests_added = False
        content_files = 0
        for entry in tree:
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            raw_path = entry.get("path")
            if not isinstance(raw_path, str):
                continue
            path = _safe_repo_path(raw_path)
            if path is None or not _needs_placeholder(path):
                continue
            if path.as_posix().startswith("tests/") and not _needs_content(path):
                if tests_added:
                    continue
                tests_added = True
                selected.append((PurePosixPath("tests/.epistemic-ci-discovered"), None))
                continue
            sha = entry.get("sha") if _needs_content(path) else None
            if sha:
                content_files += 1
                if content_files > 50:
                    continue
            selected.append((path, sha if isinstance(sha, str) else None))
            if len(selected) >= 500:
                break

        with TemporaryDirectory(prefix="epistemic-ci-advisor-") as directory:
            root = Path(directory) / name
            root.mkdir()
            for path, blob_sha in selected:
                destination = root.joinpath(*path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                content = b""
                if blob_sha:
                    blob_response = await self.request(
                        "GET",
                        f"/repos/{quote(owner)}/{quote(name)}/git/blobs/{quote(blob_sha)}",
                    )
                    if blob_response.status_code != 200:
                        raise GitHubAppError("GitHub repository-blob request failed")
                    blob = blob_response.json()
                    if blob.get("encoding") != "base64":
                        raise GitHubAppError(
                            "GitHub repository blob used an unsupported encoding"
                        )
                    try:
                        content = base64.b64decode(
                            blob.get("content", ""), validate=False
                        )
                    except (TypeError, ValueError) as exc:
                        raise GitHubAppError(
                            "GitHub repository blob was malformed"
                        ) from exc
                    if len(content) > MAX_TEXT_BLOB_BYTES:
                        raise GitHubAppError(
                            "GitHub repository text blob exceeds the supported size"
                        )
                destination.write_bytes(content)
            discovery = discover_repository(root, repository_name=repository)
        discovery["tree_truncated"] = bool(tree_payload.get("truncated"))
        return commit_sha, discovery


def _format_candidates(items: list[dict[str, str]], key: str, limit: int) -> str:
    if not items:
        return "- None detected; an agent or maintainer must identify this explicitly."
    return "\n".join(
        f"- `{item[key]}` — {item.get('source') or item.get('reason')}"
        for item in items[:limit]
    )


def _setup_issue_body(
    repository: str,
    username: str,
    branch: str,
    commit_sha: str,
    discovery: dict[str, Any],
) -> str:
    commands = _format_candidates(
        discovery["verification_command_candidates"], "command", 10
    )
    artifacts = _format_candidates(discovery["artifact_candidates"], "path", 20)
    truncation = (
        "\n\n> The GitHub tree response was truncated. Treat discovery as incomplete."
        if discovery.get("tree_truncated")
        else ""
    )
    answer_template = {
        "schema": ANSWERS_SCHEMA,
        "human_confirmed": True,
        "confirmed_by": f"@{username}",
        "verification_command": ["replace", "with", "confirmed", "command"],
        "trusted_outputs": ["replace/with/confirmed/output"],
        "checked_population": "Describe the exact population or evidence.",
        "required_failures": ["Describe a planted mistake that must be rejected."],
    }
    return f"""<!-- epistemic-ci-setup:{discovery["fingerprint"]} -->
# Epistemic CI setup confirmation

Requested by @{username}. The advisor performed **read-only mechanical discovery** against
`{repository}@{commit_sha}` on branch `{branch}`. It did not execute repository code and did
not modify the repository.

Discovery fingerprint: `{discovery["fingerprint"]}`{truncation}

## Candidate verification commands

{commands}

## Candidate trusted artifacts

{artifacts}

## Human confirmation required

Please answer directly or hand this issue to a coding/review agent:

1. Which verification command represents the check people currently trust?
2. Which final files or results do people actually trust?
3. Which planted mistakes must make verification fail?
4. What exact population or evidence produced the result?

The agent should restate the answers before recording them. A completed answers file has this
shape:

```json
{json.dumps(answer_template, indent=2)}
```

Next, follow
[`EPISTEMIC-CI-SETUP.md`](https://github.com/Silentpartnercoding/epistemic-ci/blob/main/EPISTEMIC-CI-SETUP.md)
to implement the smallest adapters and open a draft PR under repository-owned authority.

## Boundary

Discovery proposes mechanics only. Human confirmation records intended meaning; it does not
prove identity, truth, representativeness, or independence. The hosted advisor does not request
repository write, Actions, administration, secret, or merge permissions.
"""


async def _handle_setup(
    settings: Settings,
    payload: dict[str, Any],
    transport: httpx.AsyncBaseTransport | None,
) -> None:
    installation_id = payload["installation"]["id"]
    repository = payload["repository"]["full_name"]
    branch = payload["repository"].get("default_branch") or "main"
    username = payload["sender"]["login"]
    issue_number = payload["issue"]["number"]
    client = GitHubInstallationClient(settings, installation_id, transport)
    try:
        permission = await client.collaborator_permission(repository, username)
        if permission not in ALLOWED_PERMISSIONS:
            await client.add_comment(
                repository,
                issue_number,
                "Epistemic CI setup requires repository `write`, `maintain`, or `admin` "
                "permission from the person issuing the command. No repository changes were made.",
            )
            return
        commit_sha, discovery = await client.repository_snapshot(repository, branch)
        body = _setup_issue_body(repository, username, branch, commit_sha, discovery)
        setup_url = await client.create_issue(
            repository,
            "Epistemic CI setup: confirm the evidence boundary",
            body,
        )
        await client.add_comment(
            repository,
            issue_number,
            f"Read-only discovery completed. Continue setup in {setup_url}",
        )
    except Exception:
        LOGGER.exception("Epistemic CI setup processing failed for %s", repository)
        try:
            await client.add_comment(
                repository,
                issue_number,
                "Epistemic CI could not complete read-only discovery. No repository changes "
                "were made. Check the app configuration and retry with a new command.",
            )
        except Exception:
            LOGGER.exception("Unable to report Epistemic CI setup failure")


def create_app(
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    store: DeliveryStore | None = None,
) -> FastAPI:
    application = FastAPI(
        title="Epistemic CI Advisor",
        version="0.4.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    active_store = store

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "epistemic-ci-advisor"}

    @application.post("/github/webhook")
    async def webhook(
        request: Request, background_tasks: BackgroundTasks
    ) -> JSONResponse:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
                if declared_length < 0:
                    raise ValueError
                if declared_length > MAX_WEBHOOK_BYTES:
                    raise HTTPException(
                        status_code=413, detail="webhook payload too large"
                    )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="invalid content length"
                ) from exc
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > MAX_WEBHOOK_BYTES:
                raise HTTPException(status_code=413, detail="webhook payload too large")
            chunks.extend(chunk)
        body = bytes(chunks)
        active_settings = settings or Settings.from_environment()
        if not _verify_signature(
            body,
            request.headers.get("x-hub-signature-256"),
            active_settings.webhook_secret,
        ):
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        delivery = request.headers.get("x-github-delivery")
        if not delivery or not re.fullmatch(r"[A-Za-z0-9-]{1,128}", delivery):
            raise HTTPException(status_code=400, detail="invalid delivery identifier")
        nonlocal active_store
        if active_store is None:
            active_store = DeliveryStore(active_settings.delivery_db)
        if not active_store.claim(delivery):
            return JSONResponse({"status": "duplicate"}, status_code=202)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON payload") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="invalid JSON payload")
        event = request.headers.get("x-github-event")
        if event == "ping":
            return JSONResponse({"status": "pong"})
        comment = payload.get("comment")
        if (
            event != "issue_comment"
            or payload.get("action") != "created"
            or not isinstance(comment, dict)
            or not _setup_command(comment.get("body"))
        ):
            return JSONResponse({"status": "ignored"}, status_code=202)
        if not _valid_setup_payload(payload):
            raise HTTPException(status_code=400, detail="incomplete setup event")
        background_tasks.add_task(_handle_setup, active_settings, payload, transport)
        return JSONResponse({"status": "accepted"}, status_code=202)

    return application


app = create_app()
