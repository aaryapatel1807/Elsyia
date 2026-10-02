"""Local-first encrypted backup and synchronization foundation."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core import get_logger, get_settings
from app.services.tools.audit import record_tool_event

logger = get_logger("sync.manager")
_PACKAGE_PREFIX = b"ELYSIA-SYNC-V1\n"
_SCHEMA_VERSION = 1


class SyncError(RuntimeError):
    """Raised for invalid sync configuration, packages, or restore operations."""


@dataclass(frozen=True)
class SyncFileEntry:
    key: str
    target_path: str
    size_bytes: int
    digest: str
    exists: bool


@dataclass(frozen=True)
class BackupRecord:
    id: str
    filename: str
    size_bytes: int
    digest_prefix: str
    sequence: int
    device_id: str
    created_at: str
    status: str


@dataclass(frozen=True)
class BackupInspection:
    backup: BackupRecord
    schema_version: int
    device_id: str
    sequence: int
    created_at: str
    files: tuple[SyncFileEntry, ...]
    excluded: tuple[str, ...]


class SyncManager:
    """Create and restore encrypted packages without contacting a cloud service."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.project_root = Path(__file__).parents[4].resolve()
        self.backup_dir = self._resolve(self.settings.SYNC_BACKUP_DIR)
        self.db_path = self._resolve(self.settings.SYNC_DB_PATH)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    def _resolve(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path.resolve() if path.is_absolute() else (self.project_root / path).resolve()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS backups (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    digest_prefix TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    device_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'available'
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_backups_created ON backups(created_at DESC)"
            )
            connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _device_id(self) -> str:
        configured = self.settings.SYNC_DEVICE_ID.strip()
        if configured:
            return configured[:128]
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'device_id'"
            ).fetchone()
            if row is not None:
                return row["value"]
            device_id = f"device-{secrets.token_hex(12)}"
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES ('device_id', ?)", (device_id,)
            )
            connection.commit()
        return device_id

    def _fernet(self) -> Fernet:
        key = self.settings.SYNC_ENCRYPTION_KEY.strip()
        if not key:
            raise SyncError("SYNC_ENCRYPTION_KEY is required for encrypted backups")
        try:
            return Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise SyncError("SYNC_ENCRYPTION_KEY must be a valid Fernet key") from exc

    def _scope_paths(self) -> list[tuple[str, Path]]:
        configured: list[tuple[str, str]] = [
            ("memory", self.settings.MEMORY_DB_PATH),
            ("plans", self.settings.PLAN_DB_PATH),
            ("agents", self.settings.AGENTS_DB_PATH),
        ]
        attachment_dir = self._resolve(self.settings.INPUT_ATTACHMENT_DIR)
        configured.append(("input_metadata", str(attachment_dir.parent / "elysia_input.db")))
        result: list[tuple[str, Path]] = []
        seen: set[Path] = set()
        for key, raw_path in configured:
            path = self._resolve(raw_path)
            if path == self.db_path or path in seen:
                continue
            seen.add(path)
            result.append((key, path))
        return result

    @staticmethod
    def _digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _current_entries(self) -> tuple[list[SyncFileEntry], dict[str, bytes]]:
        entries: list[SyncFileEntry] = []
        contents: dict[str, bytes] = {}
        for key, path in self._scope_paths():
            if not path.exists() or not path.is_file():
                entries.append(SyncFileEntry(key, key, 0, "", False))
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise SyncError(f"Could not read the local {key} database") from exc
            if len(data) > self.settings.SYNC_MAX_PACKAGE_BYTES:
                raise SyncError(f"The local {key} database exceeds the sync package limit")
            contents[key] = data
            entries.append(SyncFileEntry(key, key, len(data), self._digest(data), True))
        return entries, contents

    def _next_sequence(self, connection: sqlite3.Connection) -> int:
        row = connection.execute("SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM backups").fetchone()
        return int(row["next_sequence"])

    @staticmethod
    def _entry_dict(entry: SyncFileEntry) -> dict[str, Any]:
        return {
            "key": entry.key,
            "target_path": entry.target_path,
            "size_bytes": entry.size_bytes,
            "digest": entry.digest,
            "exists": entry.exists,
        }

    def create_backup(self) -> BackupRecord:
        if not self.settings.SYNC_ENABLED:
            raise SyncError("Sync is disabled")
        with self._lock:
            entries, contents = self._current_entries()
            created_at = self._now()
            device_id = self._device_id()
            with closing(self._connect()) as connection:
                sequence = self._next_sequence(connection)
            manifest = {
                "schema_version": _SCHEMA_VERSION,
                "device_id": device_id,
                "sequence": sequence,
                "created_at": created_at,
                "files": [self._entry_dict(entry) for entry in entries],
                "excluded": [
                    ".env and API keys",
                    "raw input attachment files",
                    "logs, browser profiles, model caches, and temporary files",
                    "sync database and backup packages",
                ],
            }
            payload = {
                "manifest": manifest,
                "files": {
                    key: base64.b64encode(data).decode("ascii") for key, data in contents.items()
                },
            }
            encrypted = _PACKAGE_PREFIX + self._fernet().encrypt(
                json.dumps(payload, separators=(",", ":")).encode("utf-8")
            )
            if len(encrypted) > self.settings.SYNC_MAX_PACKAGE_BYTES:
                raise SyncError("Encrypted backup exceeds the configured package limit")
            backup_id = secrets.token_urlsafe(16)
            filename = f"elysia-backup-{sequence}-{backup_id}.sync"
            destination = self.backup_dir / filename
            temporary = self.backup_dir / f".{filename}.{secrets.token_hex(4)}.tmp"
            try:
                temporary.write_bytes(encrypted)
                temporary.replace(destination)
            except OSError as exc:
                temporary.unlink(missing_ok=True)
                raise SyncError("Could not write the encrypted backup package") from exc
            record = BackupRecord(
                id=backup_id,
                filename=filename,
                size_bytes=len(encrypted),
                digest_prefix=self._digest(encrypted)[:16],
                sequence=sequence,
                device_id=device_id,
                created_at=created_at,
                status="available",
            )
            with closing(self._connect()) as connection:
                connection.execute(
                    "INSERT INTO backups(id, filename, size_bytes, digest_prefix, sequence, device_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (record.id, record.filename, record.size_bytes, record.digest_prefix, record.sequence, record.device_id, record.created_at, record.status),
                )
                connection.commit()
            self._prune_backups()
        record_tool_event(
            tool_name="sync.backup",
            status="success",
            arguments={"backup_id": record.id, "sequence": record.sequence, "file_count": len(contents)},
            result={"status": "created", "size_bytes": record.size_bytes},
        )
        return record

    def _prune_backups(self) -> None:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, filename FROM backups ORDER BY created_at DESC"
            ).fetchall()
            for row in rows[self.settings.SYNC_MAX_BACKUPS :]:
                try:
                    (self.backup_dir / row["filename"]).unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove old backup package %s", row["filename"])
                connection.execute("DELETE FROM backups WHERE id = ?", (row["id"],))
            connection.commit()

    def _record_from_row(self, row: sqlite3.Row) -> BackupRecord:
        return BackupRecord(
            id=row["id"],
            filename=row["filename"],
            size_bytes=row["size_bytes"],
            digest_prefix=row["digest_prefix"],
            sequence=row["sequence"],
            device_id=row["device_id"],
            created_at=row["created_at"],
            status=row["status"],
        )

    @property
    def device_id(self) -> str:
        return self._device_id()

    def latest_backup(self) -> BackupRecord | None:
        backups = self.list_backups()
        return backups[0] if backups else None

    def read_backup_package(self, backup_id: str) -> bytes:
        record = self._get_backup(backup_id)
        try:
            data = (self.backup_dir / record.filename).read_bytes()
        except OSError as exc:
            raise SyncError("Backup package could not be read") from exc
        if len(data) > self.settings.SYNC_MAX_PACKAGE_BYTES:
            raise SyncError("Backup package exceeds the configured size limit")
        return data

    def list_backups(self) -> list[BackupRecord]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM backups ORDER BY created_at DESC").fetchall()
        records: list[BackupRecord] = []
        for row in rows:
            record = self._record_from_row(row)
            if not (self.backup_dir / record.filename).is_file():
                continue
            records.append(record)
        return records

    def _get_backup(self, backup_id: str) -> BackupRecord:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM backups WHERE id = ?", (backup_id,)).fetchone()
        if row is None:
            raise SyncError("Backup package was not found")
        record = self._record_from_row(row)
        if not (self.backup_dir / record.filename).is_file():
            raise SyncError("Backup package is missing")
        return record

    def _decode_encrypted_bytes(self, encrypted: bytes) -> dict[str, Any]:
        if len(encrypted) > self.settings.SYNC_MAX_PACKAGE_BYTES:
            raise SyncError("Backup package exceeds the configured size limit")
        if not encrypted.startswith(_PACKAGE_PREFIX):
            raise SyncError("Backup package format is invalid")
        try:
            plaintext = self._fernet().decrypt(encrypted[len(_PACKAGE_PREFIX) :])
            payload = json.loads(plaintext.decode("utf-8"))
        except (InvalidToken, UnicodeError, json.JSONDecodeError) as exc:
            raise SyncError("Backup package could not be authenticated or decoded") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("manifest"), dict) or not isinstance(payload.get("files"), dict):
            raise SyncError("Backup package payload is invalid")
        manifest = payload["manifest"]
        if manifest.get("schema_version") != _SCHEMA_VERSION:
            raise SyncError("Backup schema version is unsupported")
        return payload

    def _decode_package(self, record: BackupRecord) -> dict[str, Any]:
        package_path = self.backup_dir / record.filename
        try:
            encrypted = package_path.read_bytes()
        except OSError as exc:
            raise SyncError("Backup package could not be read") from exc
        return self._decode_encrypted_bytes(encrypted)

    def import_package(self, encrypted: bytes) -> BackupRecord:
        """Validate an encrypted remote package and store it as a local backup."""
        payload = self._decode_encrypted_bytes(encrypted)
        manifest = payload["manifest"]
        files = payload["files"]
        for raw in manifest.get("files", []):
            if not isinstance(raw, dict) or not raw.get("exists"):
                continue
            key = raw.get("key")
            encoded = files.get(key)
            if not isinstance(encoded, str):
                raise SyncError("Remote package is missing a declared database")
            try:
                data = base64.b64decode(encoded.encode("ascii"), validate=True)
            except (ValueError, UnicodeError) as exc:
                raise SyncError("Remote package contains invalid file encoding") from exc
            if self._digest(data) != raw.get("digest"):
                raise SyncError("Remote package file digest does not match its manifest")
        backup_id = secrets.token_urlsafe(16)
        filename = f"elysia-remote-{manifest.get('sequence', 0)}-{backup_id}.sync"
        destination = self.backup_dir / filename
        temporary = self.backup_dir / f".{filename}.{secrets.token_hex(4)}.tmp"
        try:
            temporary.write_bytes(encrypted)
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise SyncError("Could not store the pulled encrypted package") from exc
        record = BackupRecord(
            id=backup_id,
            filename=filename,
            size_bytes=len(encrypted),
            digest_prefix=self._digest(encrypted)[:16],
            sequence=int(manifest.get("sequence", 0)),
            device_id=str(manifest.get("device_id", "")),
            created_at=str(manifest.get("created_at", self._now())),
            status="remote",
        )
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO backups(id, filename, size_bytes, digest_prefix, sequence, device_id, created_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (record.id, record.filename, record.size_bytes, record.digest_prefix, record.sequence, record.device_id, record.created_at, record.status),
            )
            connection.commit()
        self._prune_backups()
        return record

    def inspect_backup(self, backup_id: str) -> BackupInspection:
        record = self._get_backup(backup_id)
        payload = self._decode_package(record)
        manifest = payload["manifest"]
        files: list[SyncFileEntry] = []
        for raw in manifest.get("files", []):
            if not isinstance(raw, dict) or not isinstance(raw.get("key"), str):
                raise SyncError("Backup manifest contains an invalid file entry")
            files.append(
                SyncFileEntry(
                    key=raw["key"],
                    target_path=str(raw.get("target_path", raw["key"])),
                    size_bytes=int(raw.get("size_bytes", 0)),
                    digest=str(raw.get("digest", "")),
                    exists=bool(raw.get("exists", False)),
                )
            )
        return BackupInspection(
            backup=record,
            schema_version=int(manifest["schema_version"]),
            device_id=str(manifest.get("device_id", "")),
            sequence=int(manifest.get("sequence", 0)),
            created_at=str(manifest.get("created_at", "")),
            files=tuple(files),
            excluded=tuple(str(item) for item in manifest.get("excluded", [])),
        )

    def _target_map(self) -> dict[str, Path]:
        return dict(self._scope_paths())

    def preview_restore(self, backup_id: str) -> dict[str, Any]:
        inspection = self.inspect_backup(backup_id)
        targets = self._target_map()
        files: list[dict[str, Any]] = []
        conflicts: list[str] = []
        for entry in inspection.files:
            target = targets.get(entry.key)
            if target is None:
                raise SyncError(f"Backup contains an unknown target key: {entry.key}")
            current_digest = ""
            if target.is_file():
                current_digest = self._digest(target.read_bytes())
            state = "create" if not target.exists() else ("unchanged" if current_digest == entry.digest else "conflict")
            if state == "conflict":
                conflicts.append(entry.key)
            files.append({"key": entry.key, "state": state, "size_bytes": entry.size_bytes})
        return {
            "backup_id": backup_id,
            "device_id": inspection.device_id,
            "sequence": inspection.sequence,
            "created_at": inspection.created_at,
            "files": files,
            "conflicts": conflicts,
            "requires_confirmation": True,
        }

    def resolve_conflicts(self, backup_id: str, decisions: dict[str, str]) -> dict[str, Any]:
        """Validate metadata-only conflict decisions; no plaintext is returned."""
        preview = self.preview_restore(backup_id)
        conflicts = set(preview["conflicts"])
        if set(decisions) != conflicts:
            raise SyncError("Conflict decisions must cover exactly every conflicting database key")
        allowed = {"keep_local", "use_remote", "skip"}
        if any(value not in allowed for value in decisions.values()):
            raise SyncError("Conflict decisions must be keep_local, use_remote, or skip")
        return {
            "backup_id": backup_id,
            "conflicts": [{"key": key, "decision": decisions[key]} for key in sorted(conflicts)],
            "status": "ready",
            "requires_confirmation": True,
        }

    def restore(
        self,
        backup_id: str,
        *,
        confirm: bool,
        force: bool = False,
        decisions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise SyncError("Restore requires explicit confirmation")
        preview = self.preview_restore(backup_id)
        conflicts = preview["conflicts"]
        if conflicts:
            if decisions is not None:
                self.resolve_conflicts(backup_id, decisions)
            elif not force:
                raise SyncError("Restore has conflicts; resolve each conflict or explicitly set force=true")
        record = self._get_backup(backup_id)
        payload = self._decode_package(record)
        targets = self._target_map()
        safety_dir = self.backup_dir / f"pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
        safety_dir.mkdir(parents=True, exist_ok=False)
        staged: list[tuple[Path, Path]] = []
        try:
            for entry in preview["files"]:
                key = entry["key"]
                if key in conflicts and decisions and decisions.get(key) in {"keep_local", "skip"}:
                    continue
                target = targets[key]
                if target.is_file():
                    shutil.copy2(target, safety_dir / f"{key}.db")
                encoded = payload["files"].get(key)
                if encoded is None:
                    continue
                data = base64.b64decode(encoded.encode("ascii"), validate=True)
                if self._digest(data) != next(item.digest for item in self.inspect_backup(backup_id).files if item.key == key):
                    raise SyncError("Backup file digest validation failed")
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.{secrets.token_hex(4)}.restore")
                temporary.write_bytes(data)
                staged.append((temporary, target))
            for temporary, target in staged:
                temporary.replace(target)
        except Exception as exc:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)
            raise SyncError(f"Restore failed; original files were preserved in {safety_dir.name}") from exc
        record_tool_event(
            tool_name="sync.restore",
            status="success",
            arguments={"backup_id": backup_id, "force": force},
            result={"status": "restored", "file_count": len(staged)},
        )
        return {"backup_id": backup_id, "restored": len(staged), "safety_backup": safety_dir.name}


_manager: SyncManager | None = None


def get_sync_manager() -> SyncManager:
    global _manager
    if _manager is None:
        _manager = SyncManager()
    return _manager
