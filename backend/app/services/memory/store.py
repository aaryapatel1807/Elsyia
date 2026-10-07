"""Local persistent memory storage with versioned semantic vectors and privacy controls."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Optional
from uuid import UUID, uuid4

from app.core import get_logger, get_settings
from app.services.memory.embeddings import cosine_similarity, embed_for_memory
from app.services.memory.privacy import MemoryCipher, MemoryEncryptionError

logger = get_logger("memory.store")
_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


@dataclass(frozen=True)
class MemoryRecord:
    """A single persisted memory record."""

    id: UUID
    scope: str
    content: str
    category: str
    created_at: str
    updated_at: str
    source: str = "explicit"
    approved: bool = True


class MemoryStore:
    """SQLite memory store designed for low-latency local retrieval."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.is_absolute():
            self.db_path = Path(__file__).parents[4] / self.db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()
        if get_settings().MEMORY_RETENTION_DAYS > 0:
            self.expire_old()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    @contextmanager
    def _connection_scope(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection_scope() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    embedding TEXT,
                    embedding_version TEXT NOT NULL DEFAULT 'legacy',
                    source TEXT NOT NULL DEFAULT 'explicit',
                    approved INTEGER NOT NULL DEFAULT 1,
                    encrypted INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(memories)")
            }
            migrations = {
                "embedding": "ALTER TABLE memories ADD COLUMN embedding TEXT",
                "embedding_version": "ALTER TABLE memories ADD COLUMN embedding_version TEXT NOT NULL DEFAULT 'legacy'",
                "source": "ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'explicit'",
                "approved": "ALTER TABLE memories ADD COLUMN approved INTEGER NOT NULL DEFAULT 1",
                "encrypted": "ALTER TABLE memories ADD COLUMN encrypted INTEGER NOT NULL DEFAULT 0",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(statement)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_scope_updated "
                "ON memories(scope, updated_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_scope_approved "
                "ON memories(scope, approved, updated_at DESC)"
            )
        logger.info("Memory store initialized at %s", self.db_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token.lower() for token in _TOKEN_RE.findall(value) if len(token) > 1}

    @staticmethod
    def _row_to_record(row: sqlite3.Row, content: str | None = None) -> MemoryRecord:
        return MemoryRecord(
            id=UUID(row["id"]),
            scope=row["scope"],
            content=content if content is not None else row["content"],
            category=row["category"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source=row["source"] if "source" in row.keys() else "explicit",
            approved=bool(row["approved"]) if "approved" in row.keys() else True,
        )

    @staticmethod
    def _normalize_scope(scope: str) -> str:
        return (scope.strip() or "default")[:100]

    def _cipher(self) -> MemoryCipher | None:
        try:
            return MemoryCipher.from_settings()
        except MemoryEncryptionError:
            raise

    def _decode_content(self, row: sqlite3.Row) -> str:
        content = row["content"]
        if int(row["encrypted"] or 0):
            cipher = self._cipher()
            if cipher is None:
                raise MemoryEncryptionError(
                    "Memory content is encrypted; configure MEMORY_ENCRYPTION_KEY"
                )
            return cipher.decrypt(content)
        return content

    def save(
        self,
        content: str,
        scope: str = "default",
        category: str = "general",
        *,
        source: str = "explicit",
        approved: bool = True,
    ) -> MemoryRecord:
        """Persist one memory, encrypting content when a key is configured."""
        settings = get_settings()
        normalized = " ".join(content.strip().split())
        if not normalized:
            raise ValueError("Memory content cannot be empty")
        normalized = normalized[: settings.MEMORY_MAX_CONTENT_LENGTH]
        scope = self._normalize_scope(scope)
        category = (category.strip() or "general")[:50]
        source = (source.strip() or "explicit")[:30]
        memory_id = uuid4()
        timestamp = self._now()
        cipher = self._cipher()
        stored_content = cipher.encrypt(normalized) if cipher else normalized
        embedding = json.dumps(embed_for_memory(normalized), separators=(",", ":"))
        with self._lock, self._connection_scope() as connection:
            connection.execute(
                "INSERT INTO memories(id, scope, content, category, created_at, updated_at, "
                "embedding, embedding_version, source, approved, encrypted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(memory_id),
                    scope,
                    stored_content,
                    category,
                    timestamp,
                    timestamp,
                    embedding,
                    settings.MEMORY_EMBEDDING_VERSION,
                    source,
                    int(approved),
                    int(cipher is not None),
                ),
            )
        return MemoryRecord(memory_id, scope, normalized, category, timestamp, timestamp, source, approved)

    def search(self, query: str, scope: str = "default", limit: Optional[int] = None) -> list[MemoryRecord]:
        """Return approved memories ranked by neural and lexical relevance."""
        settings = get_settings()
        max_results = limit or settings.MEMORY_MAX_RESULTS
        scope = self._normalize_scope(scope)
        with self._connection_scope() as connection:
            rows = connection.execute(
                "SELECT id, scope, content, category, created_at, updated_at, embedding, "
                "embedding_version, source, approved, encrypted FROM memories "
                "WHERE scope = ? AND approved = 1 ORDER BY updated_at DESC LIMIT 250",
                (scope,),
            ).fetchall()
        query_tokens = self._tokens(query)
        query_vector = embed_for_memory(query)
        ranked: list[tuple[float, int, MemoryRecord]] = []
        stale_updates: list[tuple[str, str, str]] = []
        for index, row in enumerate(rows):
            content = self._decode_content(row)
            record = self._row_to_record(row, content)
            try:
                stored_vector = json.loads(row["embedding"]) if row["embedding"] else []
            except (TypeError, json.JSONDecodeError):
                stored_vector = []
            if (
                not stored_vector
                or len(stored_vector) != len(query_vector)
                or row["embedding_version"] != settings.MEMORY_EMBEDDING_VERSION
            ):
                stored_vector = embed_for_memory(record.content)
                # Persist the refreshed vector: recomputing on every search
                # is a repeated tax, writing it back is a one-time cost.
                stale_updates.append((
                    json.dumps(stored_vector, separators=(",", ":")),
                    settings.MEMORY_EMBEDDING_VERSION,
                    row["id"],
                ))
            semantic_score = cosine_similarity(query_vector, stored_vector)
            lexical_score = len(query_tokens & self._tokens(record.content)) / max(len(query_tokens), 1)
            combined_score = 0.8 * semantic_score + 0.2 * lexical_score
            if combined_score >= 0.30 or not query_tokens:
                ranked.append((combined_score, -index, record))
        if stale_updates:
            with self._lock, self._connection_scope() as connection:
                connection.executemany(
                    "UPDATE memories SET embedding = ?, embedding_version = ? "
                    "WHERE id = ?",
                    stale_updates,
                )
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[:max_results]]

    def list(
        self,
        scope: str = "default",
        limit: int = 100,
        *,
        include_pending: bool = False,
    ) -> list[MemoryRecord]:
        """List memories for the current scope, optionally including pending records."""
        scope = self._normalize_scope(scope)
        approval_clause = "" if include_pending else " AND approved = 1"
        with self._connection_scope() as connection:
            rows = connection.execute(
                "SELECT id, scope, content, category, created_at, updated_at, source, approved, encrypted "
                f"FROM memories WHERE scope = ?{approval_clause} ORDER BY updated_at DESC LIMIT ?",
                (scope, min(max(limit, 1), 500)),
            ).fetchall()
        return [self._row_to_record(row, self._decode_content(row)) for row in rows]

    def approve(self, memory_id: UUID, scope: str = "default") -> bool:
        """Approve one pending memory for retrieval."""
        with self._lock, self._connection_scope() as connection:
            result = connection.execute(
                "UPDATE memories SET approved = 1, updated_at = ? WHERE id = ? AND scope = ?",
                (self._now(), str(memory_id), self._normalize_scope(scope)),
            )
        return result.rowcount > 0

    def delete(self, memory_id: UUID, scope: str = "default") -> bool:
        """Delete one memory only when it belongs to the requested scope."""
        with self._lock, self._connection_scope() as connection:
            result = connection.execute(
                "DELETE FROM memories WHERE id = ? AND scope = ?",
                (str(memory_id), self._normalize_scope(scope)),
            )
        return result.rowcount > 0

    def clear(self, scope: str = "default") -> int:
        """Delete all memories in one scope and return the deleted count."""
        with self._lock, self._connection_scope() as connection:
            result = connection.execute(
                "DELETE FROM memories WHERE scope = ?", (self._normalize_scope(scope),)
            )
        return result.rowcount

    def expire_old(self, scope: str | None = None) -> int:
        """Delete memories older than configured retention days."""
        days = get_settings().MEMORY_RETENTION_DAYS
        if days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock, self._connection_scope() as connection:
            if scope:
                result = connection.execute(
                    "DELETE FROM memories WHERE scope = ? AND updated_at < ?",
                    (self._normalize_scope(scope), cutoff),
                )
            else:
                result = connection.execute("DELETE FROM memories WHERE updated_at < ?", (cutoff,))
        return result.rowcount

    def reindex(self, scope: str | None = None) -> int:
        """Rebuild stored neural vectors for all memories or one scope."""
        settings = get_settings()
        with self._connection_scope() as connection:
            if scope:
                rows = connection.execute(
                    "SELECT id, content, encrypted FROM memories WHERE scope = ?",
                    (self._normalize_scope(scope),),
                ).fetchall()
            else:
                rows = connection.execute("SELECT id, content, encrypted FROM memories").fetchall()
        updates: list[tuple[str, str, str]] = []
        for row in rows:
            content = self._decode_content(row)
            vector = json.dumps(embed_for_memory(content), separators=(",", ":"))
            updates.append((vector, settings.MEMORY_EMBEDDING_VERSION, row["id"]))
        with self._lock, self._connection_scope() as connection:
            connection.executemany(
                "UPDATE memories SET embedding = ?, embedding_version = ?, updated_at = updated_at WHERE id = ?",
                updates,
            )
        return len(updates)

    def export(self, scope: str = "default") -> list[dict[str, str | bool]]:
        """Return decrypted, user-visible memory data for export or backup."""
        return [
            {
                "id": str(record.id),
                "scope": record.scope,
                "content": record.content,
                "category": record.category,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "source": record.source,
                "approved": record.approved,
            }
            for record in self.list(scope, limit=500)
        ]

    def stats(self, scope: str = "default") -> dict[str, int | str | bool]:
        """Return privacy-safe memory statistics without content."""
        with self._connection_scope() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN approved = 0 THEN 1 ELSE 0 END) AS pending, "
                "SUM(CASE WHEN embedding_version = ? AND approved = 1 THEN 1 ELSE 0 END) AS indexed "
                "FROM memories WHERE scope = ?",
                (get_settings().MEMORY_EMBEDDING_VERSION, self._normalize_scope(scope)),
            ).fetchone()
        return {
            "scope": self._normalize_scope(scope),
            "total": int(row["total"] or 0) - int(row["pending"] or 0),
            "pending": int(row["pending"] or 0),
            "indexed": int(row["indexed"] or 0),
            "encrypted": bool(self._cipher()),
        }


_memory_store: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    """Return the process-wide configured memory store."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore(get_settings().MEMORY_DB_PATH)
    return _memory_store
