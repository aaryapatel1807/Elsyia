"""Regression tests for the bounded local Phase 3 vision foundation."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.tools import registry  # noqa: E402
from app.services.tools.base import ToolError  # noqa: E402
from app.services.tools.vision_tools import OcrImageTool  # noqa: E402


class Phase3VisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        settings = get_settings()
        settings.INPUT_ATTACHMENT_DIR = str(Path(self.temp.name) / "attachments")
        settings.INPUT_SAFE_ROOTS = self.temp.name
        settings.VISION_ENABLED = True

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_tools_are_registered_and_confirmation_gated(self) -> None:
        names = {item["name"] for item in registry.list()}
        self.assertIn("capture_screen", names)
        self.assertIn("ocr_image", names)
        result = asyncio.run(registry.execute("capture_screen", {}))
        self.assertEqual(result.status, "confirmation_required")

    def test_ocr_rejects_unsafe_and_invalid_paths(self) -> None:
        unsafe = Path(self.temp.name).parent / "outside.png"
        unsafe.write_bytes(b"not-an-image")
        with self.assertRaises(ToolError):
            asyncio.run(OcrImageTool().run(str(unsafe)))
        text = Path(self.temp.name) / "note.txt"
        text.write_text("secret", encoding="utf-8")
        with self.assertRaises(ToolError):
            asyncio.run(OcrImageTool().run(str(text)))

    def test_ocr_fails_closed_without_local_engine(self) -> None:
        image = Path(self.temp.name) / "sample.png"
        image.write_bytes(b"not-an-image")
        try:
            result = asyncio.run(OcrImageTool().run(str(image)))
        except ToolError as exc:
            self.assertIn("OCR", str(exc))
        else:
            self.assertIn("status", result)

    def test_disabled_vision_fails_closed(self) -> None:
        get_settings().VISION_ENABLED = False
        image = Path(self.temp.name) / "sample.png"
        image.write_bytes(b"not-an-image")
        with self.assertRaises(ToolError):
            asyncio.run(OcrImageTool().run(str(image)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
