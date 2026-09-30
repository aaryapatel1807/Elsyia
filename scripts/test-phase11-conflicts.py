"""Regression checks for explicit provider-neutral sync conflict resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from cryptography.fernet import Fernet  # noqa: E402
from app.core import get_settings  # noqa: E402
from app.services.sync.manager import SyncError, SyncManager  # noqa: E402


class Phase11ConflictTests(unittest.TestCase):
    def test_conflicts_require_explicit_metadata_only_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            settings = get_settings()
            settings.SYNC_ENABLED = True
            settings.SYNC_ENCRYPTION_KEY = Fernet.generate_key().decode()
            settings.SYNC_BACKUP_DIR = str(root / "backups")
            settings.SYNC_DB_PATH = str(root / "sync.db")
            settings.MEMORY_DB_PATH = str(root / "memory.db")
            settings.PLAN_DB_PATH = str(root / "plans.db")
            settings.AGENTS_DB_PATH = str(root / "agents.db")
            settings.INPUT_ATTACHMENT_DIR = str(root / "attachments")
            (root / "memory.db").write_bytes(b"remote-state")
            manager = SyncManager()
            backup = manager.create_backup()
            (root / "memory.db").write_bytes(b"local-state")
            preview = manager.preview_restore(backup.id)
            self.assertEqual(preview["conflicts"], ["memory"])
            with self.assertRaises(SyncError):
                manager.resolve_conflicts(backup.id, {})
            with self.assertRaises(SyncError):
                manager.resolve_conflicts(backup.id, {"memory": "last_write_wins"})
            resolution = manager.resolve_conflicts(backup.id, {"memory": "keep_local"})
            self.assertEqual(resolution["status"], "ready")
            restored = manager.restore(
                backup.id,
                confirm=True,
                decisions={"memory": "keep_local"},
            )
            self.assertEqual(restored["restored"], 0)
            self.assertEqual((root / "memory.db").read_bytes(), b"local-state")


if __name__ == "__main__":
    unittest.main(verbosity=2)
