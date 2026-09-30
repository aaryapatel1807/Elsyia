"""Authentication and transport policy for encrypted Phase 11 sync packages."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse, urlunparse

import httpx

from app.core import get_settings


class SyncAuthError(RuntimeError):
    """Raised when authentication, endpoint policy, or transport validation fails."""


def _body_digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_request(
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    request_id: str,
    body_digest: str,
) -> bytes:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return "\n".join(
        [method.upper(), normalized_path, timestamp, nonce, request_id, body_digest]
    ).encode("utf-8")


def sign_request(
    *,
    method: str,
    path: str,
    body: bytes,
    token: str,
    timestamp: str,
    nonce: str,
    request_id: str,
) -> str:
    if not token:
        raise SyncAuthError("SYNC_AUTH_TOKEN is required for cloud transport")
    message = _canonical_request(
        method, path, timestamp, nonce, request_id, _body_digest(body)
    )
    return hmac.new(token.encode("utf-8"), message, hashlib.sha256).hexdigest()


def build_auth_headers(
    *,
    method: str,
    path: str,
    body: bytes,
    device_id: str,
    token: str,
    timestamp: str | None = None,
    nonce: str | None = None,
    request_id: str | None = None,
) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    nonce = nonce or secrets.token_urlsafe(24)
    request_id = request_id or secrets.token_urlsafe(24)
    digest = _body_digest(body)
    signature = sign_request(
        method=method,
        path=path,
        body=body,
        token=token,
        timestamp=timestamp,
        nonce=nonce,
        request_id=request_id,
    )
    return {
        "Authorization": f"Elysia-HMAC {signature}",
        "X-Elysia-Device": device_id,
        "X-Elysia-Request-Id": request_id,
        "X-Elysia-Timestamp": timestamp,
        "X-Elysia-Nonce": nonce,
        "X-Elysia-Body-SHA256": digest,
        "Content-Type": "application/octet-stream",
    }


class ReplayGuard:
    """Thread-safe replay cache suitable for a relay request verifier."""

    def __init__(self, window_seconds: int = 900) -> None:
        self.window_seconds = window_seconds
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def check_and_record(self, request_id: str, nonce: str, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        with self._lock:
            cutoff = now - self.window_seconds
            self._seen = {key: value for key, value in self._seen.items() if value >= cutoff}
            for value in (f"id:{request_id}", f"nonce:{nonce}"):
                if value in self._seen:
                    raise SyncAuthError("Sync request replay detected")
            self._seen[f"id:{request_id}"] = now
            self._seen[f"nonce:{nonce}"] = now


def verify_signed_request(
    *,
    method: str,
    path: str,
    body: bytes,
    headers: dict[str, str],
    token: str,
    device_id: str,
    replay_guard: ReplayGuard,
    clock_skew_seconds: int = 300,
    now: int | None = None,
) -> None:
    """Verify a signed relay request without accepting plaintext sync data."""
    required = {
        "X-Elysia-Device",
        "X-Elysia-Request-Id",
        "X-Elysia-Timestamp",
        "X-Elysia-Nonce",
        "X-Elysia-Body-SHA256",
        "Authorization",
    }
    if not required.issubset(headers):
        raise SyncAuthError("Sync authentication headers are incomplete")
    if headers["X-Elysia-Device"] != device_id:
        raise SyncAuthError("Unknown sync device")
    try:
        timestamp = int(headers["X-Elysia-Timestamp"])
    except ValueError as exc:
        raise SyncAuthError("Sync timestamp is invalid") from exc
    now = now if now is not None else int(time.time())
    if abs(now - timestamp) > clock_skew_seconds:
        raise SyncAuthError("Sync request timestamp is outside the allowed clock skew")
    digest = _body_digest(body)
    if not hmac.compare_digest(headers["X-Elysia-Body-SHA256"], digest):
        raise SyncAuthError("Sync request body digest does not match")
    expected = sign_request(
        method=method,
        path=path,
        body=body,
        token=token,
        timestamp=headers["X-Elysia-Timestamp"],
        nonce=headers["X-Elysia-Nonce"],
        request_id=headers["X-Elysia-Request-Id"],
    )
    supplied = headers["Authorization"]
    prefix = "Elysia-HMAC "
    if not supplied.startswith(prefix) or not hmac.compare_digest(supplied[len(prefix) :], expected):
        raise SyncAuthError("Sync request signature is invalid")
    replay_guard.check_and_record(headers["X-Elysia-Request-Id"], headers["X-Elysia-Nonce"], now=float(now))


class EndpointPolicy:
    """Exact-origin and HTTPS policy for cloud sync endpoints."""

    def __init__(self, settings=None) -> None:
        self.settings = settings or get_settings()

    def _allowlisted_origins(self) -> set[str]:
        raw = self.settings.SYNC_ENDPOINT_ALLOWLIST.replace(",", ";")
        return {item.strip().rstrip("/") for item in raw.split(";") if item.strip()}

    def validate(self, endpoint: str) -> tuple[str, str]:
        endpoint = endpoint.strip()
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            raise SyncAuthError("Sync endpoint must be an HTTPS URL without embedded credentials")
        if parsed.scheme == "http" and not (
            self.settings.SYNC_ALLOW_LOOPBACK_HTTP and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise SyncAuthError("HTTP sync endpoints are restricted to explicitly allowed loopback development relays")
        origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")
        if origin not in self._allowlisted_origins():
            raise SyncAuthError("Sync endpoint origin is not in SYNC_ENDPOINT_ALLOWLIST")
        path = parsed.path.rstrip("/") or ""
        return origin, path


@dataclass(frozen=True)
class TransportResult:
    status_code: int
    remote_id: str | None
    bytes_sent: int


class SyncTransport:
    """Opt-in HTTP transport for already-encrypted sync packages."""

    def __init__(self, manager, settings=None, http_client_factory: Callable[..., httpx.Client] | None = None) -> None:
        self.manager = manager
        self.settings = settings or get_settings()
        self.policy = EndpointPolicy(self.settings)
        self.http_client_factory = http_client_factory or httpx.Client

    def _check_enabled(self) -> tuple[str, str]:
        if not self.settings.SYNC_CLOUD_ENABLED:
            raise SyncAuthError("Cloud sync is disabled")
        if not self.settings.SYNC_CLOUD_ENDPOINT.strip():
            raise SyncAuthError("SYNC_CLOUD_ENDPOINT is not configured")
        if not self.settings.SYNC_AUTH_TOKEN.strip():
            raise SyncAuthError("SYNC_AUTH_TOKEN is not configured")
        return self.policy.validate(self.settings.SYNC_CLOUD_ENDPOINT)

    def _url(self, action: str) -> tuple[str, str]:
        origin, base_path = self._check_enabled()
        path = f"{base_path}/{action}" if base_path else f"/{action}"
        return f"{origin}{path}", path

    def push_latest(self) -> TransportResult:
        url, path = self._url("push")
        record = self.manager.latest_backup()
        if record is None:
            raise SyncAuthError("Create an encrypted backup before pushing")
        body = self.manager.read_backup_package(record.id)
        if len(body) > self.settings.SYNC_MAX_PUSH_BYTES:
            raise SyncAuthError("Encrypted package exceeds the push limit")
        headers = build_auth_headers(
            method="POST",
            path=path,
            body=body,
            device_id=self.manager.device_id,
            token=self.settings.SYNC_AUTH_TOKEN,
        )
        try:
            with self.http_client_factory(follow_redirects=False, timeout=self.settings.SYNC_REQUEST_TIMEOUT_SECONDS) as client:
                response = client.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise SyncAuthError("Sync push transport failed") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise SyncAuthError(f"Sync push rejected by relay with status {response.status_code}")
        remote_id = None
        try:
            remote_id = response.json().get("remote_id")
        except (ValueError, AttributeError):
            pass
        return TransportResult(response.status_code, remote_id, len(body))

    def pull(self) -> bytes:
        url, path = self._url("pull")
        headers = build_auth_headers(
            method="GET",
            path=path,
            body=b"",
            device_id=self.manager.device_id,
            token=self.settings.SYNC_AUTH_TOKEN,
        )
        try:
            with self.http_client_factory(follow_redirects=False, timeout=self.settings.SYNC_REQUEST_TIMEOUT_SECONDS) as client:
                response = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise SyncAuthError("Sync pull transport failed") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise SyncAuthError(f"Sync pull rejected by relay with status {response.status_code}")
        if len(response.content) > self.settings.SYNC_MAX_PACKAGE_BYTES:
            raise SyncAuthError("Pulled package exceeds the configured size limit")
        return response.content


__all__ = [
    "EndpointPolicy",
    "ReplayGuard",
    "SyncAuthError",
    "SyncTransport",
    "TransportResult",
    "build_auth_headers",
    "sign_request",
    "verify_signed_request",
]
