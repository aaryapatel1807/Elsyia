"""Regression tests for Phase 11 sync authentication and transport policy."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
import sys

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.sync import (  # noqa: E402
    EndpointPolicy,
    ReplayGuard,
    SyncAuthError,
    SyncManager,
    SyncTransport,
    build_auth_headers,
    verify_signed_request,
)
from app.services.sync.relay import create_relay_router  # noqa: E402


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", payload: dict | None = None) -> None:
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeClient:
    last_url = ""
    last_headers: dict[str, str] = {}
    response: FakeResponse | None = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, content, headers):
        FakeClient.last_url = url
        FakeClient.last_headers = headers
        return FakeClient.response or FakeResponse(200, payload={"remote_id": "remote-1"})

    def get(self, url, headers):
        FakeClient.last_url = url
        FakeClient.last_headers = headers
        return FakeClient.response or FakeResponse(200)


class Phase11AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = get_settings()
        self.settings.SYNC_CLOUD_ENABLED = True
        self.settings.SYNC_CLOUD_ENDPOINT = "https://sync.example.com/v1"
        self.settings.SYNC_ENDPOINT_ALLOWLIST = "https://sync.example.com"
        self.settings.SYNC_AUTH_TOKEN = "test-device-secret"
        self.settings.SYNC_ALLOW_LOOPBACK_HTTP = False
        self.settings.SYNC_CLOCK_SKEW_SECONDS = 300
        self.settings.SYNC_REPLAY_WINDOW_SECONDS = 900

    def test_sign_verify_and_replay_rejection(self) -> None:
        body = b"encrypted-package"
        headers = build_auth_headers(
            method="POST",
            path="/v1/push",
            body=body,
            device_id="device-a",
            token=self.settings.SYNC_AUTH_TOKEN,
            timestamp=str(int(time.time())),
            nonce="nonce-a",
            request_id="request-a",
        )
        guard = ReplayGuard(900)
        verify_signed_request(
            method="POST",
            path="/v1/push",
            body=body,
            headers=headers,
            token=self.settings.SYNC_AUTH_TOKEN,
            device_id="device-a",
            replay_guard=guard,
        )
        with self.assertRaises(SyncAuthError):
            verify_signed_request(
                method="POST",
                path="/v1/push",
                body=body,
                headers=headers,
                token=self.settings.SYNC_AUTH_TOKEN,
                device_id="device-a",
                replay_guard=guard,
            )

    def test_tampered_body_and_stale_timestamp_are_rejected(self) -> None:
        headers = build_auth_headers(
            method="POST",
            path="/v1/push",
            body=b"original",
            device_id="device-a",
            token=self.settings.SYNC_AUTH_TOKEN,
            timestamp=str(int(time.time()) - 1000),
            nonce="nonce-b",
            request_id="request-b",
        )
        with self.assertRaises(SyncAuthError):
            verify_signed_request(
                method="POST",
                path="/v1/push",
                body=b"tampered",
                headers=headers,
                token=self.settings.SYNC_AUTH_TOKEN,
                device_id="device-a",
                replay_guard=ReplayGuard(900),
            )
        headers = build_auth_headers(
            method="POST",
            path="/v1/push",
            body=b"original",
            device_id="device-a",
            token=self.settings.SYNC_AUTH_TOKEN,
            timestamp=str(int(time.time()) - 1000),
            nonce="nonce-c",
            request_id="request-c",
        )
        with self.assertRaises(SyncAuthError):
            verify_signed_request(
                method="POST",
                path="/v1/push",
                body=b"original",
                headers=headers,
                token=self.settings.SYNC_AUTH_TOKEN,
                device_id="device-a",
                replay_guard=ReplayGuard(900),
            )

    def test_endpoint_allowlist_and_loopback_policy(self) -> None:
        policy = EndpointPolicy(self.settings)
        origin, path = policy.validate("https://sync.example.com/v1")
        self.assertEqual(origin, "https://sync.example.com")
        self.assertEqual(path, "/v1")
        with self.assertRaises(SyncAuthError):
            policy.validate("https://evil.example.com/v1")
        with self.assertRaises(SyncAuthError):
            policy.validate("http://127.0.0.1:9000/v1")
        self.settings.SYNC_ALLOW_LOOPBACK_HTTP = True
        self.settings.SYNC_ENDPOINT_ALLOWLIST = "http://127.0.0.1:9000"
        self.assertEqual(policy.validate("http://127.0.0.1:9000/v1")[0], "http://127.0.0.1:9000")

    def test_disabled_transport_fails_before_network(self) -> None:
        self.settings.SYNC_CLOUD_ENABLED = False
        transport = SyncTransport(object(), self.settings, lambda **kwargs: (_ for _ in ()).throw(AssertionError("network called")))
        with self.assertRaises(SyncAuthError):
            transport.push_latest()

    def test_relay_authenticates_push_pull_and_rejects_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.settings.SYNC_RELAY_ENABLED = True
            self.settings.SYNC_RELAY_DB_PATH = str(root / "relay.db")
            self.settings.SYNC_RELAY_STORAGE_DIR = str(root / "packages")
            self.settings.SYNC_RELAY_SHARED_TOKEN = "relay-secret"
            self.settings.SYNC_RELAY_ALLOWED_DEVICES = "device-a"
            app = FastAPI()
            app.include_router(create_relay_router(), prefix="/relay")
            body = b"opaque-encrypted-package"
            headers = build_auth_headers(
                method="POST",
                path="/relay/push",
                body=body,
                device_id="device-a",
                token="relay-secret",
                timestamp=str(int(time.time())),
                nonce="relay-nonce-a",
                request_id="relay-request-a",
            )
            with TestClient(app) as client:
                accepted = client.post("/relay/push", content=body, headers=headers)
                self.assertEqual(accepted.status_code, 200, accepted.text)
                replayed = client.post("/relay/push", content=body, headers=headers)
                self.assertEqual(replayed.status_code, 401)
                pull_headers = build_auth_headers(
                    method="GET",
                    path="/relay/pull",
                    body=b"",
                    device_id="device-a",
                    token="relay-secret",
                    nonce="relay-nonce-b",
                    request_id="relay-request-b",
                )
                pulled = client.get("/relay/pull", headers=pull_headers)
                self.assertEqual(pulled.status_code, 200, pulled.text)
                self.assertEqual(pulled.content, body)

    def test_authenticated_push_uses_encrypted_package_and_allowlisted_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.settings.SYNC_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
            self.settings.SYNC_BACKUP_DIR = str(root / "backups")
            self.settings.SYNC_DB_PATH = str(root / "sync.db")
            self.settings.MEMORY_DB_PATH = str(root / "memory.db")
            self.settings.PLAN_DB_PATH = str(root / "plans.db")
            self.settings.AGENTS_DB_PATH = str(root / "agents.db")
            self.settings.INPUT_ATTACHMENT_DIR = str(root / "attachments")
            Path(self.settings.MEMORY_DB_PATH).write_bytes(b"memory")
            manager = SyncManager()
            manager.create_backup()
            FakeClient.response = FakeResponse(200, payload={"remote_id": "relay-123"})
            result = SyncTransport(manager, self.settings, FakeClient).push_latest()
            self.assertEqual(result.remote_id, "relay-123")
            self.assertEqual(FakeClient.last_url, "https://sync.example.com/v1/push")
            self.assertTrue(FakeClient.last_headers["Authorization"].startswith("Elysia-HMAC "))
            self.assertNotIn(self.settings.SYNC_AUTH_TOKEN, str(FakeClient.last_headers))


if __name__ == "__main__":
    unittest.main(verbosity=2)
