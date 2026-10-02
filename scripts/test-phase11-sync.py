"""Regression tests for the Phase 11 local-first sync foundation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.sync import SyncError, SyncManager  # noqa: E402


class Phase11SyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = get_settings()
        self.settings.SYNC_ENABLED = True
        self.settings.SYNC_CLOUD_ENABLED = False
        self.settings.SYNC_CLOUD_ENDPOINT = ""
        self.settings.SYNC_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
        self.settings.SYNC_DEVICE_ID = "test-device"
        self.settings.SYNC_BACKUP_DIR = str(self.root / "backups")
        self.settings.SYNC_DB_PATH = str(self.root / "sync.db")
        self.settings.SYNC_MAX_BACKUPS = 20
        self.settings.SYNC_MAX_PACKAGE_BYTES = 10_000_000
        self.settings.MEMORY_DB_PATH = str(self.root / "memory.db")
        self.settings.PLAN_DB_PATH = str(self.root / "plans.db")
        self.settings.AGENTS_DB_PATH = str(self.root / "agents.db")
        self.settings.INPUT_ATTACHMENT_DIR = str(self.root / "attachments")
        Path(self.settings.MEMORY_DB_PATH).write_bytes(b"local memory database v1")
        Path(self.settings.PLAN_DB_PATH).write_bytes(b"local plans database v1")
        Path(self.settings.AGENTS_DB_PATH).write_bytes(b"local agents database v1")
        attachment_dir = Path(self.settings.INPUT_ATTACHMENT_DIR)
        attachment_dir.mkdir()
        (attachment_dir / "raw-secret-attachment.bin").write_bytes(b"raw attachment bytes")
        (attachment_dir.parent / "elysia_input.db").write_bytes(b"input metadata v1")
        self.manager = SyncManager()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_backup_is_encrypted_and_manifest_excludes_raw_attachments(self) -> None:
        record = self.manager.create_backup()
        package = (self.manager.backup_dir / record.filename).read_bytes()
        self.assertNotIn(b"local memory database v1", package)
        self.assertNotIn(b"raw attachment bytes", package)
        inspection = self.manager.inspect_backup(record.id)
        self.assertEqual(inspection.device_id, "test-device")
        self.assertEqual(inspection.sequence, 1)
        self.assertEqual({entry.key for entry in inspection.files}, {"memory", "plans", "agents", "input_metadata"})
        self.assertIn("raw input attachment files", inspection.excluded)

    def test_preview_detects_conflict_and_restore_requires_confirmation(self) -> None:
        record = self.manager.create_backup()
        memory_path = Path(self.settings.MEMORY_DB_PATH)
        memory_path.write_bytes(b"changed local memory")
        preview = self.manager.preview_restore(record.id)
        self.assertIn("memory", preview["conflicts"])
        with self.assertRaises(SyncError):
            self.manager.restore(record.id, confirm=False)
        with self.assertRaises(SyncError):
            self.manager.restore(record.id, confirm=True, force=False)

        result = self.manager.restore(record.id, confirm=True, force=True)
        self.assertEqual(result["restored"], 4)
        self.assertEqual(memory_path.read_bytes(), b"local memory database v1")
        self.assertTrue((self.manager.backup_dir / result["safety_backup"] / "memory.db").exists())

    def test_tampered_backup_is_rejected(self) -> None:
        record = self.manager.create_backup()
        package_path = self.manager.backup_dir / record.filename
        data = bytearray(package_path.read_bytes())
        data[-1] ^= 1
        package_path.write_bytes(bytes(data))
        with self.assertRaises(SyncError):
            self.manager.inspect_backup(record.id)

    def test_invalid_key_fails_closed(self) -> None:
        self.settings.SYNC_ENCRYPTION_KEY = "not-a-fernet-key"
        with self.assertRaises(SyncError):
            self.manager.create_backup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
