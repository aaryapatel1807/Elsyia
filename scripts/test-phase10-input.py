"""Regression tests for Phase 10 normalized input and local file ingestion."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.core import get_settings  # noqa: E402
from app.services.input import AttachmentStore, InputValidationError  # noqa: E402
import app.services.input.manager as input_manager  # noqa: E402
from app.main import app  # noqa: E402


class Phase10InputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.safe = self.root / "safe"
        self.outside = self.root / "outside"
        self.safe.mkdir()
        self.outside.mkdir()
        self.settings = get_settings()
        self.settings.INPUT_ENABLED = True
        self.settings.INPUT_SAFE_ROOTS = str(self.safe)
        self.settings.INPUT_ATTACHMENT_DIR = str(self.root / "attachments")
        self.settings.INPUT_MAX_FILES_PER_DROP = 10
        self.settings.INPUT_MAX_FILE_BYTES = 100
        self.settings.INPUT_MAX_TOTAL_BYTES = 150
        self.settings.INPUT_MAX_ATTACHMENTS = 1000
        self.settings.INPUT_RETENTION_HOURS = 24
        self.settings.INPUT_ALLOWED_EXTENSIONS = ".txt,.md,.png"
        self.store = AttachmentStore()
        input_manager._store = self.store

    def tearDown(self) -> None:
        input_manager._store = None
        self.temp.cleanup()

    def test_ingest_persists_metadata_and_copies_without_modifying_original(self) -> None:
        source = self.safe / "note.txt"
        content = b"hello local-first input"
        source.write_bytes(content)
        original_mtime = source.stat().st_mtime_ns

        events = self.store.ingest_files([str(source)], conversation_id="conversation-1")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.display_name, "note.txt")
        self.assertEqual(event.size_bytes, len(content))
        self.assertEqual(source.read_bytes(), content)
        self.assertEqual(source.stat().st_mtime_ns, original_mtime)
        self.assertTrue((self.store.attachment_dir / f"{event.attachment_token}.txt").exists())
        self.assertEqual(len(self.store.list_attachments()), 1)

        reopened = AttachmentStore()
        self.assertEqual(reopened.list_attachments()[0].attachment_token, event.attachment_token)

    def test_rejects_outside_root(self) -> None:
        source = self.outside / "outside.txt"
        source.write_text("no", encoding="utf-8")
        with self.assertRaises(InputValidationError):
            self.store.ingest_files([str(source)])

    def test_rejects_extension_and_size(self) -> None:
        bad = self.safe / "run.exe"
        bad.write_bytes(b"no")
        with self.assertRaises(InputValidationError):
            self.store.ingest_files([str(bad)])

        large = self.safe / "large.txt"
        large.write_bytes(b"x" * 101)
        with self.assertRaises(InputValidationError):
            self.store.ingest_files([str(large)])

    def test_rejects_symlink_when_supported(self) -> None:
        source = self.safe / "real.txt"
        source.write_text("real", encoding="utf-8")
        link = self.safe / "link.txt"
        try:
            link.symlink_to(source)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable on this host")
        with self.assertRaises(InputValidationError):
            self.store.ingest_files([str(link)])

    def test_multi_file_total_limit_and_deletion(self) -> None:
        first = self.safe / "one.txt"
        second = self.safe / "two.txt"
        first.write_bytes(b"a" * 75)
        second.write_bytes(b"b" * 75)
        events = self.store.ingest_files([str(first), str(second)])
        self.assertEqual(len(events), 2)
        self.assertTrue(self.store.delete_attachment(events[0].attachment_token))
        self.assertEqual(len(self.store.list_attachments()), 1)
        self.assertFalse(self.store.delete_attachment("missing-token"))

        third = self.safe / "three.txt"
        third.write_bytes(b"c" * 76)
        with self.assertRaises(InputValidationError):
            self.store.ingest_files([str(first), str(third)])

    def test_expiry_cleanup_removes_copy_and_marks_record(self) -> None:
        source = self.safe / "expire.txt"
        source.write_text("expire", encoding="utf-8")
        event = self.store.ingest_files([str(source)])[0]
        stored = self.store.attachment_dir / f"{event.attachment_token}.txt"
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            connection.execute(
                "UPDATE attachments SET expires_at = '2000-01-01T00:00:00+00:00' WHERE token = ?",
                (event.attachment_token,),
            )
            connection.commit()
        self.assertEqual(self.store.clear_expired(), 1)
        self.assertFalse(stored.exists())
        self.assertEqual(self.store.list_attachments(), [])
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            status = connection.execute(
                "SELECT status FROM attachments WHERE token = ?", (event.attachment_token,)
            ).fetchone()[0]
        self.assertEqual(status, "expired")

    def test_api_ingest_list_delete_and_cleanup(self) -> None:
        source = self.safe / "api.txt"
        source.write_text("api", encoding="utf-8")
        with TestClient(app) as client:
            response = client.post("/api/v1/input/ingest", json={"paths": [str(source)]})
            self.assertEqual(response.status_code, 201, response.text)
            token = response.json()[0]["token"]
            listed = client.get("/api/v1/input/attachments")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(listed.json()["attachments"][0]["token"], token)
            deleted = client.delete(f"/api/v1/input/attachments/{token}")
            self.assertEqual(deleted.status_code, 204)
            self.assertEqual(client.get("/api/v1/input/attachments").json()["attachments"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
