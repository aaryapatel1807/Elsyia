"""Optional self-hosted relay for opaque encrypted Phase 11 packages."""

from __future__ import annotations

import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.core import get_settings
from app.services.sync.auth import ReplayGuard, SyncAuthError, verify_signed_request


class RelayStore:
    """Persistent opaque-package storage and request replay registry."""

    def __init__(self) -> None:
        settings = get_settings()
        self.project_root = Path(__file__).parents[4].resolve()
        db_path = Path(settings.SYNC_RELAY_DB_PATH)
        self.db_path = db_path.resolve() if db_path.is_absolute() else (self.project_root / db_path).resolve()
        storage_dir = Path(settings.SYNC_RELAY_STORAGE_DIR)
        self.storage_dir = storage_dir.resolve() if storage_dir.is_absolute() else (self.project_root / storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS packages (id TEXT PRIMARY KEY, device_id TEXT NOT NULL, created_at TEXT NOT NULL, path TEXT NOT NULL, digest TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS replay (value TEXT PRIMARY KEY, created_at INTEGER NOT NULL)"
            )
            connection.commit()

    def record_replay(self, request_id: str, nonce: str, now: int, window: int) -> None:
        cutoff = now - window
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM replay WHERE created_at < ?", (cutoff,))
            for value in (f"id:{request_id}", f"nonce:{nonce}"):
                if connection.execute("SELECT 1 FROM replay WHERE value = ?", (value,)).fetchone():
                    raise SyncAuthError("Sync request replay detected")
            connection.executemany("INSERT INTO replay(value, created_at) VALUES (?, ?)", [(f"id:{request_id}", now), (f"nonce:{nonce}", now)])
            connection.commit()

    def store(self, device_id: str, package: bytes, digest: str) -> str:
        package_id = secrets.token_urlsafe(18)
        filename = f"{package_id}.sync"
        temporary = self.storage_dir / f".{filename}.tmp"
        destination = self.storage_dir / filename
        temporary.write_bytes(package)
        temporary.replace(destination)
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO packages(id, device_id, created_at, path, digest) VALUES (?, ?, ?, ?, ?)",
                (package_id, device_id, datetime.now(timezone.utc).isoformat(), filename, digest),
            )
            connection.commit()
        return package_id

    def latest(self, device_id: str | None = None) -> bytes | None:
        with closing(self._connect()) as connection:
            if device_id:
                row = connection.execute("SELECT path FROM packages WHERE device_id = ? ORDER BY created_at DESC LIMIT 1", (device_id,)).fetchone()
            else:
                row = connection.execute("SELECT path FROM packages ORDER BY created_at DESC LIMIT 1").fetchone()
        if row is None:
            return None
        path = self.storage_dir / row["path"]
        return path.read_bytes() if path.is_file() else None


def _allowed_devices() -> set[str]:
    return {item.strip() for item in get_settings().SYNC_RELAY_ALLOWED_DEVICES.replace(",", ";").split(";") if item.strip()}


def create_relay_router() -> APIRouter:
    router = APIRouter()
    store = RelayStore()
    replay_guard = ReplayGuard(get_settings().SYNC_REPLAY_WINDOW_SECONDS)

    def authenticate(method: str, path: str, body: bytes, device: str, request_id: str, timestamp: str, nonce: str, body_digest: str, authorization: str) -> None:
        settings = get_settings()
        if not settings.SYNC_RELAY_ENABLED:
            raise HTTPException(status_code=404, detail="Sync relay disabled")
        if not settings.SYNC_RELAY_SHARED_TOKEN:
            raise HTTPException(status_code=503, detail="Sync relay authentication is not configured")
        allowed = _allowed_devices()
        if allowed and device not in allowed:
            raise HTTPException(status_code=403, detail="Device is not enrolled")
        headers = {
            "X-Elysia-Device": device,
            "X-Elysia-Request-Id": request_id,
            "X-Elysia-Timestamp": timestamp,
            "X-Elysia-Nonce": nonce,
            "X-Elysia-Body-SHA256": body_digest,
            "Authorization": authorization,
        }
        try:
            verify_signed_request(
                method=method,
                path=path,
                body=body,
                headers=headers,
                token=settings.SYNC_RELAY_SHARED_TOKEN,
                device_id=device,
                replay_guard=replay_guard,
                clock_skew_seconds=settings.SYNC_CLOCK_SKEW_SECONDS,
            )
            store.record_replay(request_id, nonce, int(timestamp), settings.SYNC_REPLAY_WINDOW_SECONDS)
        except (SyncAuthError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Sync authentication failed") from exc

    @router.post("/push")
    async def push(
        request: Request,
        x_elysia_device: str = Header(default=""),
        x_elysia_request_id: str = Header(default=""),
        x_elysia_timestamp: str = Header(default=""),
        x_elysia_nonce: str = Header(default=""),
        x_elysia_body_sha256: str = Header(default=""),
        authorization: str = Header(default=""),
    ) -> dict[str, str]:
        body = await request.body()
        settings = get_settings()
        if len(body) > settings.SYNC_RELAY_MAX_PACKAGE_BYTES:
            raise HTTPException(status_code=413, detail="Sync package is too large")
        authenticate("POST", request.url.path, body, x_elysia_device, x_elysia_request_id, x_elysia_timestamp, x_elysia_nonce, x_elysia_body_sha256, authorization)
        package_id = store.store(x_elysia_device, body, x_elysia_body_sha256)
        return {"accepted": "true", "remote_id": package_id}

    @router.get("/pull")
    async def pull(
        request: Request,
        x_elysia_device: str = Header(default=""),
        x_elysia_request_id: str = Header(default=""),
        x_elysia_timestamp: str = Header(default=""),
        x_elysia_nonce: str = Header(default=""),
        x_elysia_body_sha256: str = Header(default=""),
        authorization: str = Header(default=""),
    ) -> Response:
        body = await request.body()
        authenticate("GET", request.url.path, body, x_elysia_device, x_elysia_request_id, x_elysia_timestamp, x_elysia_nonce, x_elysia_body_sha256, authorization)
        package = store.latest()
        if package is None:
            raise HTTPException(status_code=404, detail="No encrypted package is available")
        return Response(content=package, media_type="application/octet-stream")

    return router


__all__ = ["RelayStore", "create_relay_router"]
