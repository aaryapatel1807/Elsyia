"""Regression checks for managed clipboard, camera, and handwriting adapters."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.input.manager import AttachmentStore, InputValidationError  # noqa: E402
from app.services.tools.base import ToolError  # noqa: E402
from app.services.tools.vision_tools import OcrImageTool  # noqa: E402


class Phase10AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        settings = get_settings()
        settings.INPUT_ENABLED = True
        settings.INPUT_ATTACHMENT_DIR = str(Path(self.temp.name) / "attachments")
        settings.INPUT_PROCESSING_ENABLED = False
        settings.INPUT_PROCESSING_AUTO_SUMMARY = False
        settings.INPUT_ALLOWED_EXTENSIONS = ".txt,.png,.jpg,.jpeg,.webp,.gif"
        settings.INPUT_MAX_FILE_BYTES = 1024 * 1024
        settings.VISION_ENABLED = True
        self.store = AttachmentStore()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_clipboard_and_camera_are_managed_attachments(self) -> None:
        clipboard = self.store.ingest_bytes(
            "private clipboard text".encode(),
            display_name="clipboard.txt",
            source="clipboard",
        )
        camera = self.store.ingest_bytes(
            b"fake png bytes",
            display_name="..\\camera.png",
            source="camera",
            kind="image",
            mime_type="image/png",
        )
        self.assertEqual(clipboard.source, "clipboard")
        self.assertEqual(camera.source, "camera")
        self.assertEqual(camera.display_name, "camera.png")
        self.assertTrue(self.store.get_attachment_path(camera.attachment_token).is_file())
        self.assertEqual(len(self.store.list_attachments()), 2)
        self.assertTrue(self.store.delete_attachment(clipboard.attachment_token))

    def test_byte_adapter_rejects_unapproved_extensions_and_ocr_fails_closed(self) -> None:
        with self.assertRaises(InputValidationError):
            self.store.ingest_bytes(b"bad", display_name="payload.exe", source="camera", kind="image")
        image = self.store.ingest_bytes(
            b"not a real image",
            display_name="handwriting.png",
            source="camera",
            kind="image",
            mime_type="image/png",
        )
        try:
            result = asyncio.run(OcrImageTool().run(str(self.store.get_attachment_path(image.attachment_token))))
        except ToolError as exc:
            self.assertIn("OCR", str(exc))
        else:
            self.assertIn("status", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
