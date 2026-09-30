"""Verify privacy and migration controls for Phase 2 memory."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.fernet import Fernet


def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        db_path = str(Path(temporary_dir) / "memory.db")
        os.environ["ENABLE_MEMORY"] = "true"
        os.environ["MEMORY_DB_PATH"] = db_path
        os.environ["MEMORY_EMBEDDING_PROVIDER"] = "local"
        os.environ["MEMORY_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        os.environ["MEMORY_RETENTION_DAYS"] = "0"

        from app.services.memory.store import MemoryStore

        store = MemoryStore(db_path)
        saved = store.save("Aarya prefers dark mode.", category="preference")
        assert store.stats()["encrypted"] is True
        assert store.stats()["pending"] == 0
        assert store.search("Aarya prefers dark mode")[0].content == "Aarya prefers dark mode."
        assert store.reindex() == 1
        assert store.export()[0]["content"] == "Aarya prefers dark mode."

        reopened = MemoryStore(db_path)
        assert reopened.list()[0].id == saved.id
        assert reopened.delete(saved.id) is True
        assert reopened.list() == []

    print("memory hardening checks passed")


if __name__ == "__main__":
    main()
