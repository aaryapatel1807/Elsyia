"""Local-first normalized input and secure attachment storage."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core import get_logger, get_settings
from app.services.tools.audit import record_tool_event

logger = get_logger("input.manager")


class InputValidationError(ValueError):
    """Raised when an input attachment violates the local file policy."""


@dataclass(frozen=True)
class ProcessingJob:
    id: str
    attachment_token: str
    status: str
    summary: str | None
    error: str | None
    extracted_chars: int
    truncated: bool
    provider: str | None
    memory_proposal_ids: tuple[str, ...]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class InputEvent:
    id: str
    source: str
    kind: str
    conversation_id: str | None
    attachment_token: str
    display_name: str
    extension: str
    mime_type: str
    size_bytes: int
    digest_prefix: str
    privacy: str
    retention: str
    created_at: str
    expires_at: str
    status: str = "active"
    processing_job: ProcessingJob | None = None


class AttachmentStore:
    """SQLite-backed attachment metadata and private copied-file store."""

    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self.project_root = Path(__file__).parents[4].resolve()
        attachment_dir = Path(settings.INPUT_ATTACHMENT_DIR)
        if not attachment_dir.is_absolute():
            attachment_dir = self.project_root / attachment_dir
        self.attachment_dir = attachment_dir.resolve()
        self.db_path = self.attachment_dir.parent / "elysia_input.db"
        self.attachment_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS attachments (
                    token TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    conversation_id TEXT,
                    display_name TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    digest_prefix TEXT NOT NULL,
                    stored_name TEXT NOT NULL,
                    privacy TEXT NOT NULL,
                    retention TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_attachments_expiry ON attachments(status, expires_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processing_jobs (
                    id TEXT PRIMARY KEY,
                    attachment_token TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    summary TEXT,
                    error TEXT,
                    extracted_chars INTEGER NOT NULL DEFAULT 0,
                    truncated INTEGER NOT NULL DEFAULT 0,
                    provider TEXT,
                    memory_proposal_ids TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (attachment_token) REFERENCES attachments(token)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status, created_at)"
            )
            connection.commit()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    def _allowed_extensions(self) -> set[str]:
        raw = getattr(self.settings, "INPUT_ALLOWED_EXTENSIONS", "")
        return {
            item.strip().lower() if item.strip().startswith(".") else f".{item.strip().lower()}"
            for item in raw.split(",")
            if item.strip()
        }

    def _safe_roots(self) -> list[Path]:
        raw = getattr(self.settings, "INPUT_SAFE_ROOTS", "")
        roots = []
        for item in raw.replace(",", ";").split(";"):
            if item.strip():
                roots.append(Path(item.strip()).expanduser().resolve())
        return roots

    def _validate_source_path(self, raw_path: str) -> Path:
        if not raw_path or "\x00" in raw_path:
            raise InputValidationError("Invalid file path")
        candidate = Path(raw_path).expanduser()
        try:
            if candidate.is_symlink():
                raise InputValidationError("Symbolic links are not accepted")
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise InputValidationError("File does not exist") from exc
        except OSError as exc:
            raise InputValidationError("File path could not be resolved") from exc
        if not resolved.is_file():
            raise InputValidationError("Only regular files can be ingested")
        roots = self._safe_roots()
        if not roots:
            raise InputValidationError("No INPUT_SAFE_ROOTS configured")
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise InputValidationError("File is outside configured safe roots")
        try:
            if resolved.is_symlink():
                raise InputValidationError("Symbolic links are not accepted")
        except OSError as exc:
            raise InputValidationError("File could not be inspected safely") from exc
        return resolved

    def _classify(self, path: Path) -> tuple[str, str]:
        extension = path.suffix.lower()
        if extension not in self._allowed_extensions():
            raise InputValidationError(f"File extension is not allowed: {extension or '<none>'}")
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if extension in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            kind = "image"
        elif extension in {".wav", ".mp3", ".m4a"}:
            kind = "audio"
        elif extension in {".mp4", ".webm"}:
            kind = "video"
        elif extension == ".pdf":
            kind = "document"
        else:
            kind = "text"
        return kind, mime_type

    def ingest_bytes(
        self,
        content: bytes,
        *,
        display_name: str,
        source: str,
        conversation_id: str | None = None,
        kind: str = "text",
        mime_type: str = "text/plain",
    ) -> InputEvent:
        """Store trusted in-process bytes as one managed private attachment."""
        if not self.settings.INPUT_ENABLED:
            raise InputValidationError("Multimodal input is disabled")
        if not content or len(content) > self.settings.INPUT_MAX_FILE_BYTES:
            raise InputValidationError("Input payload is empty or exceeds the per-file limit")
        if kind not in {"text", "image", "audio", "video", "document"}:
            raise InputValidationError("Unsupported input kind")
        safe_name = Path(display_name).name.strip() or "input.bin"
        extension = Path(safe_name).suffix.lower()
        if extension not in self._allowed_extensions():
            raise InputValidationError(f"File extension is not allowed: {extension or '<none>'}")
        with closing(self._connect()) as connection:
            active_count = connection.execute(
                "SELECT COUNT(*) FROM attachments WHERE status = 'active'"
            ).fetchone()[0]
            if active_count >= self.settings.INPUT_MAX_ATTACHMENTS:
                raise InputValidationError("Attachment storage limit reached")
            token = secrets.token_urlsafe(18)
            event_id = secrets.token_hex(16)
            stored_name = f"{token}{extension}"
            destination = self.attachment_dir / stored_name
            destination.write_bytes(content)
            created = self._now()
            expires = created + timedelta(hours=self.settings.INPUT_RETENTION_HOURS)
            digest = hashlib.sha256(content).hexdigest()
            event = InputEvent(
                id=event_id,
                source=source,
                kind=kind,
                conversation_id=conversation_id,
                attachment_token=token,
                display_name=safe_name[:255],
                extension=extension,
                mime_type=mime_type[:120],
                size_bytes=len(content),
                digest_prefix=digest[:16],
                privacy="sensitive" if kind in {"audio", "video", "image"} else "private",
                retention="expires",
                created_at=self._iso(created),
                expires_at=self._iso(expires),
            )
            connection.execute(
                """INSERT INTO attachments (token, event_id, source, kind, conversation_id, display_name,
                   extension, mime_type, size_bytes, digest_prefix, stored_name, privacy, retention,
                   created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (token, event.id, event.source, event.kind, event.conversation_id, event.display_name,
                 event.extension, event.mime_type, event.size_bytes, event.digest_prefix, stored_name,
                 event.privacy, event.retention, event.created_at, event.expires_at, event.status),
            )
            connection.commit()
        if self.settings.INPUT_PROCESSING_ENABLED and self.settings.INPUT_PROCESSING_AUTO_SUMMARY and kind == "text":
            try:
                event = replace(event, processing_job=self.enqueue_processing(event.attachment_token))
            except Exception as exc:
                logger.warning("Could not queue byte attachment processing: %s", exc)
        record_tool_event(
            tool_name="input.ingest_bytes",
            status="success",
            arguments={"source": source, "kind": kind, "display_name": "<redacted>", "size_bytes": len(content)},
            result={"status": "stored", "attachment_token": token},
        )
        return event

    @staticmethod
    def _row_to_job(row: sqlite3.Row | None) -> ProcessingJob | None:
        if row is None:
            return None
        try:
            proposal_ids = tuple(str(item) for item in json.loads(row["memory_proposal_ids"] or "[]"))
        except (TypeError, json.JSONDecodeError):
            proposal_ids = ()
        return ProcessingJob(
            id=row["id"],
            attachment_token=row["attachment_token"],
            status=row["status"],
            summary=row["summary"],
            error=row["error"],
            extracted_chars=int(row["extracted_chars"] or 0),
            truncated=bool(row["truncated"]),
            provider=row["provider"],
            memory_proposal_ids=proposal_ids,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_event(self, row: sqlite3.Row, processing_job: ProcessingJob | None = None) -> InputEvent:
        return InputEvent(
            id=row["event_id"],
            source=row["source"],
            kind=row["kind"],
            conversation_id=row["conversation_id"],
            attachment_token=row["token"],
            display_name=row["display_name"],
            extension=row["extension"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            digest_prefix=row["digest_prefix"],
            privacy=row["privacy"],
            retention=row["retention"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            status=row["status"],
            processing_job=processing_job,
        )

    def get_processing_job(self, job_id: str) -> ProcessingJob | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM processing_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row_to_job(row)

    def get_latest_processing_job(self, token: str) -> ProcessingJob | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM processing_jobs WHERE attachment_token = ? ORDER BY created_at DESC LIMIT 1",
                (token,),
            ).fetchone()
        return self._row_to_job(row)

    def enqueue_processing(self, token: str, *, force: bool = False) -> ProcessingJob:
        now = self._iso(self._now())
        with closing(self._connect()) as connection:
            attachment = connection.execute(
                "SELECT token, status FROM attachments WHERE token = ? AND status = 'active'",
                (token,),
            ).fetchone()
            if attachment is None:
                raise InputValidationError("Attachment not found or expired")
            latest = connection.execute(
                "SELECT * FROM processing_jobs WHERE attachment_token = ? ORDER BY created_at DESC LIMIT 1",
                (token,),
            ).fetchone()
            if latest is not None and not force and latest["status"] in {"queued", "running", "completed"}:
                return self._row_to_job(latest)  # type: ignore[return-value]
            job_id = secrets.token_hex(16)
            connection.execute(
                "INSERT INTO processing_jobs (id, attachment_token, status, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)",
                (job_id, token, now, now),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
        record_tool_event(
            tool_name="input.process",
            status="queued",
            arguments={"attachment_token": token, "job_id": job_id},
            result={"status": "queued"},
        )
        return self._row_to_job(row)  # type: ignore[return-value]

    def next_queued_processing_job(self) -> ProcessingJob | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM processing_jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                "UPDATE processing_jobs SET status = 'running', updated_at = ? WHERE id = ? AND status = 'queued'",
                (self._iso(self._now()), row["id"]),
            )
            connection.commit()
            if updated.rowcount != 1:
                return None
            row = connection.execute("SELECT * FROM processing_jobs WHERE id = ?", (row["id"],)).fetchone()
        return self._row_to_job(row)

    def update_processing_job(
        self,
        job_id: str,
        *,
        status: str,
        summary: str | None = None,
        error: str | None = None,
        extracted_chars: int = 0,
        truncated: bool = False,
        provider: str | None = None,
        memory_proposal_ids: tuple[str, ...] = (),
    ) -> ProcessingJob | None:
        now = self._iso(self._now())
        with closing(self._connect()) as connection:
            connection.execute(
                """UPDATE processing_jobs SET status = ?, summary = ?, error = ?, extracted_chars = ?,
                   truncated = ?, provider = ?, memory_proposal_ids = ?, updated_at = ? WHERE id = ?""",
                (status, summary, error, extracted_chars, int(truncated), provider,
                 json.dumps(list(memory_proposal_ids)), now, job_id),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row)

    def read_attachment_text(self, token: str, max_chars: int) -> tuple[str, bool, str]:
        text_extensions = {
            ".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".py", ".js", ".jsx",
            ".ts", ".tsx", ".java", ".c", ".h", ".cpp", ".hpp", ".go", ".rs",
        }
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT stored_name, extension, display_name FROM attachments WHERE token = ? AND status = 'active'",
                (token,),
            ).fetchone()
        if row is None:
            raise InputValidationError("Attachment not found or expired")
        if row["extension"].lower() not in text_extensions:
            raise InputValidationError("This attachment type has no local text processor yet")
        stored_path = (self.attachment_dir / row["stored_name"]).resolve()
        if self.attachment_dir not in stored_path.parents or stored_path.is_symlink() or not stored_path.is_file():
            raise InputValidationError("Attachment storage path is invalid")
        try:
            with stored_path.open("r", encoding="utf-8", errors="replace") as handle:
                content = handle.read(max_chars + 1)
        except OSError as exc:
            raise InputValidationError("Attachment could not be read") from exc
        return content[:max_chars], len(content) > max_chars, row["display_name"]

    def ingest_files(
        self,
        paths: list[str],
        *,
        conversation_id: str | None = None,
        source: str = "desktop_drop",
    ) -> list[InputEvent]:
        if not self.settings.INPUT_ENABLED:
            raise InputValidationError("Multimodal input is disabled")
        if not paths:
            raise InputValidationError("At least one file is required")
        if len(paths) > self.settings.INPUT_MAX_FILES_PER_DROP:
            raise InputValidationError(
                f"A drop may contain at most {self.settings.INPUT_MAX_FILES_PER_DROP} files"
            )

        candidates = [self._validate_source_path(item) for item in paths]
        total_size = 0
        inspected: list[tuple[Path, str, str, int]] = []
        for path in candidates:
            size = path.stat().st_size
            if size > self.settings.INPUT_MAX_FILE_BYTES:
                raise InputValidationError(f"File exceeds per-file limit: {path.name}")
            total_size += size
            kind, mime_type = self._classify(path)
            inspected.append((path, kind, mime_type, size))
        if total_size > self.settings.INPUT_MAX_TOTAL_BYTES:
            raise InputValidationError("Drop exceeds total byte limit")

        with closing(self._connect()) as connection:
            active_count = connection.execute(
                "SELECT COUNT(*) FROM attachments WHERE status = 'active'"
            ).fetchone()[0]
            if active_count + len(inspected) > self.settings.INPUT_MAX_ATTACHMENTS:
                raise InputValidationError("Attachment storage limit reached")

            events: list[InputEvent] = []
            copied: list[Path] = []
            try:
                for source_path, kind, mime_type, size in inspected:
                    token = secrets.token_urlsafe(18)
                    event_id = secrets.token_hex(16)
                    stored_name = f"{token}{source_path.suffix.lower()}"
                    destination = self.attachment_dir / stored_name
                    copied_bytes = 0
                    with source_path.open("rb") as input_file, destination.open("xb") as output_file:
                        digest = hashlib.sha256()
                        while True:
                            chunk = input_file.read(1024 * 1024)
                            if not chunk:
                                break
                            copied_bytes += len(chunk)
                            if copied_bytes > self.settings.INPUT_MAX_FILE_BYTES:
                                raise InputValidationError(f"File exceeds per-file limit: {source_path.name}")
                            digest.update(chunk)
                            output_file.write(chunk)
                    if copied_bytes != size:
                        raise InputValidationError(f"File changed during ingestion: {source_path.name}")
                    copied.append(destination)
                    created = self._now()
                    expires = created + timedelta(hours=self.settings.INPUT_RETENTION_HOURS)
                    event = InputEvent(
                        id=event_id,
                        source=source,
                        kind=kind,
                        conversation_id=conversation_id,
                        attachment_token=token,
                        display_name=source_path.name,
                        extension=source_path.suffix.lower(),
                        mime_type=mime_type,
                        size_bytes=size,
                        digest_prefix=digest.hexdigest()[:16],
                        privacy="sensitive" if kind in {"audio", "video"} else "private",
                        retention="expires",
                        created_at=self._iso(created),
                        expires_at=self._iso(expires),
                    )
                    connection.execute(
                        """
                        INSERT INTO attachments (
                            token, event_id, source, kind, conversation_id, display_name,
                            extension, mime_type, size_bytes, digest_prefix, stored_name,
                            privacy, retention, created_at, expires_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            token, event.id, event.source, event.kind, event.conversation_id,
                            event.display_name, event.extension, event.mime_type, event.size_bytes,
                            event.digest_prefix, stored_name, event.privacy, event.retention,
                            event.created_at, event.expires_at, event.status,
                        ),
                    )
                    events.append(event)
                connection.commit()
            except Exception:
                for copied_path in copied:
                    try:
                        copied_path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Could not remove partial attachment %s", copied_path)
                raise

        for index, event in enumerate(events):
            if self.settings.INPUT_PROCESSING_ENABLED and self.settings.INPUT_PROCESSING_AUTO_SUMMARY:
                try:
                    queued_job = self.enqueue_processing(event.attachment_token)
                    events[index] = replace(event, processing_job=queued_job)
                except Exception as exc:
                    logger.warning("Could not queue attachment processing: %s", exc)
            record_tool_event(
                tool_name="input.ingest",
                status="success",
                arguments={
                    "source": event.source,
                    "kind": event.kind,
                    "display_name": "<redacted>",
                    "size_bytes": event.size_bytes,
                    "digest_prefix": event.digest_prefix,
                },
                result={"status": "stored", "attachment_token": event.attachment_token},
            )
        return events

    def list_attachments(self, *, include_expired: bool = False) -> list[InputEvent]:
        self.clear_expired()
        query = "SELECT * FROM attachments"
        parameters: tuple[Any, ...] = ()
        if not include_expired:
            query += " WHERE status = 'active'"
        query += " ORDER BY created_at DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_event(row, self.get_latest_processing_job(row["token"])) for row in rows]

    def get_attachment_path(self, token: str) -> Path:
        row = self._find_active(token)
        if row is None:
            raise InputValidationError("Attachment not found or expired")
        stored_path = (self.attachment_dir / row["stored_name"]).resolve()
        if self.attachment_dir not in stored_path.parents or stored_path.is_symlink() or not stored_path.is_file():
            raise InputValidationError("Attachment storage path is invalid")
        return stored_path

    def _find_active(self, token: str) -> sqlite3.Row | None:
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT * FROM attachments WHERE token = ? AND status = 'active'", (token,)
            ).fetchone()

    def delete_attachment(self, token: str) -> bool:
        row = self._find_active(token)
        if row is None:
            return False
        path = self.attachment_dir / row["stored_name"]
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not delete attachment copy %s: %s", path, exc)
        with closing(self._connect()) as connection:
            connection.execute("UPDATE attachments SET status = 'deleted' WHERE token = ?", (token,))
            connection.commit()
        record_tool_event(
            tool_name="input.delete",
            status="success",
            arguments={"attachment_token": token},
            result={"status": "deleted"},
        )
        return True

    def clear_expired(self) -> int:
        now = self._iso(self._now())
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT token, stored_name FROM attachments WHERE status = 'active' AND expires_at <= ?",
                (now,),
            ).fetchall()
            for row in rows:
                try:
                    (self.attachment_dir / row["stored_name"]).unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Could not remove expired attachment %s: %s", row["stored_name"], exc)
                connection.execute(
                    "UPDATE attachments SET status = 'expired' WHERE token = ?", (row["token"],)
                )
            connection.commit()
        if rows:
            record_tool_event(
                tool_name="input.cleanup",
                status="success",
                arguments={"expired_count": len(rows)},
                result={"status": "cleaned"},
            )
        return len(rows)


_store: AttachmentStore | None = None


def get_attachment_store() -> AttachmentStore:
    global _store
    if _store is None:
        _store = AttachmentStore()
    return _store
