from __future__ import annotations

import base64
import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import httpx
    from fastapi.testclient import TestClient

    from epistemic_ci.github_app import (
        DeliveryStore,
        GitHubInstallationClient,
        Settings,
        create_app,
    )

    APP_DEPENDENCIES = True
except ImportError:
    APP_DEPENDENCIES = False


@unittest.skipUnless(APP_DEPENDENCIES, "install the github-app optional dependencies")
class GitHubAppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.settings = Settings(
            app_id="123",
            private_key="unused-in-tests",
            webhook_secret="test-webhook-secret",
            api_url="https://api.github.test",
            delivery_db=str(Path(self.temporary.name) / "deliveries.sqlite3"),
        )
        self.requests: list[tuple[str, str, dict[str, object] | None]] = []
        self.permission = "write"

        blobs = {
            "workflow-sha": "steps:\n  - run: python -m unittest discover -s tests -v\n",
            "project-sha": '[project]\nname = "sample"\n',
        }

        def handler(request: httpx.Request) -> httpx.Response:
            request_json = None
            if request.content:
                request_json = json.loads(request.content)
            self.requests.append((request.method, request.url.path, request_json))
            path = request.url.path
            if path == "/app/installations/77/access_tokens":
                return httpx.Response(201, json={"token": "installation-token"})
            if path.endswith("/collaborators/alice/permission"):
                return httpx.Response(200, json={"permission": self.permission})
            if path.endswith("/commits/main"):
                return httpx.Response(
                    200,
                    json={"sha": "commit-sha", "commit": {"tree": {"sha": "tree-sha"}}},
                )
            if path.endswith("/git/trees/tree-sha"):
                return httpx.Response(
                    200,
                    json={
                        "sha": "tree-sha",
                        "truncated": False,
                        "tree": [
                            {
                                "path": ".github/workflows/ci.yml",
                                "type": "blob",
                                "sha": "workflow-sha",
                            },
                            {
                                "path": "pyproject.toml",
                                "type": "blob",
                                "sha": "project-sha",
                            },
                            {
                                "path": "results/final-report.json",
                                "type": "blob",
                                "sha": "report-sha",
                            },
                            {
                                "path": "tests/test_sample.py",
                                "type": "blob",
                                "sha": "test-sha",
                            },
                        ],
                    },
                )
            if "/git/blobs/" in path:
                sha = path.rsplit("/", 1)[-1]
                return httpx.Response(
                    200,
                    json={
                        "encoding": "base64",
                        "content": base64.b64encode(blobs[sha].encode()).decode(),
                    },
                )
            if path == "/repos/acme/sample/issues" and request.method == "POST":
                return httpx.Response(
                    201,
                    json={"html_url": "https://github.test/acme/sample/issues/101"},
                )
            if (
                path == "/repos/acme/sample/issues/9/comments"
                and request.method == "POST"
            ):
                return httpx.Response(201, json={"id": 1})
            return httpx.Response(404, json={"message": "not found"})

        self.transport = httpx.MockTransport(handler)
        self.store = DeliveryStore(self.settings.delivery_db)
        app = create_app(self.settings, self.transport, self.store)
        self.client = TestClient(app)

    def _payload(self, command: str = "/epistemic-ci setup") -> bytes:
        return json.dumps(
            {
                "action": "created",
                "installation": {"id": 77},
                "repository": {"full_name": "acme/sample", "default_branch": "main"},
                "sender": {"login": "alice"},
                "issue": {"number": 9},
                "comment": {"body": command},
            }
        ).encode()

    def _headers(self, body: bytes, delivery: str = "delivery-1") -> dict[str, str]:
        signature = (
            "sha256="
            + hmac.new(
                self.settings.webhook_secret.encode(), body, hashlib.sha256
            ).hexdigest()
        )
        return {
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": delivery,
            "X-GitHub-Event": "issue_comment",
            "Content-Type": "application/json",
        }

    def test_health_does_not_require_github_credentials(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_invalid_signature_is_rejected_before_processing(self) -> None:
        body = self._payload()
        headers = self._headers(body)
        headers["X-Hub-Signature-256"] = "sha256:" + ("0" * 64)
        response = self.client.post("/github/webhook", content=body, headers=headers)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.requests, [])

    def test_non_setup_comment_is_ignored_without_github_api_calls(self) -> None:
        body = self._payload("ordinary discussion")
        response = self.client.post(
            "/github/webhook",
            content=body,
            headers=self._headers(body),
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "ignored")
        self.assertEqual(self.requests, [])

    def test_malformed_repository_is_rejected_before_github_api_calls(self) -> None:
        payload = json.loads(self._payload())
        payload["repository"]["full_name"] = "not-a-full-name"
        body = json.dumps(payload).encode()
        response = self.client.post(
            "/github/webhook",
            content=body,
            headers=self._headers(body),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.requests, [])

    def test_authorized_setup_creates_issue_from_read_only_discovery(self) -> None:
        body = self._payload()
        with patch.object(
            GitHubInstallationClient, "_app_jwt", return_value="app-token"
        ):
            response = self.client.post(
                "/github/webhook",
                content=body,
                headers=self._headers(body),
            )
        self.assertEqual(response.status_code, 202)
        created = [
            request
            for request in self.requests
            if request[0] == "POST" and request[1] == "/repos/acme/sample/issues"
        ]
        self.assertEqual(len(created), 1)
        issue_body = created[0][2]["body"]
        self.assertIn("commit-sha", issue_body)
        self.assertIn("python -m unittest discover -s tests -v", issue_body)
        self.assertIn("results/final-report.json", issue_body)
        self.assertIn("did not execute repository code", issue_body)
        fetched_paths = [path for method, path, _ in self.requests if method == "GET"]
        self.assertNotIn("/repos/acme/sample/git/blobs/report-sha", fetched_paths)

    def test_sender_without_write_permission_cannot_start_discovery(self) -> None:
        self.permission = "read"
        body = self._payload()
        with patch.object(
            GitHubInstallationClient, "_app_jwt", return_value="app-token"
        ):
            response = self.client.post(
                "/github/webhook",
                content=body,
                headers=self._headers(body),
            )
        self.assertEqual(response.status_code, 202)
        self.assertFalse(any("/git/trees/" in path for _, path, _ in self.requests))
        comments = [
            request
            for request in self.requests
            if request[1] == "/repos/acme/sample/issues/9/comments"
        ]
        self.assertEqual(len(comments), 1)
        self.assertIn("requires repository `write`", comments[0][2]["body"])

    def test_duplicate_delivery_is_not_processed_twice(self) -> None:
        body = self._payload("ordinary discussion")
        headers = self._headers(body, delivery="same-delivery")
        first = self.client.post("/github/webhook", content=body, headers=headers)
        second = self.client.post("/github/webhook", content=body, headers=headers)
        self.assertEqual(first.json()["status"], "ignored")
        self.assertEqual(second.json()["status"], "duplicate")


if __name__ == "__main__":
    unittest.main()
