"""Regression tests for guarded browser screenshots and downloads."""

from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.browser import BrowserSessionError, browser_manager  # noqa: E402
from app.services.browser.manager import BrowserSession  # noqa: E402
from app.services.tools import registry  # noqa: E402


class FakePage:
    def __init__(self, payload: bytes = b"png") -> None:
        self.payload = payload
        self.url = "https://example.com/page"
        self.download = None

    async def screenshot(self, *, path: str, **_: object) -> None:
        Path(path).write_bytes(self.payload)

    async def goto(self, url: str, *, wait_until: str) -> None:
        self.url = url

    def expect_download(self, *, timeout: int) -> "DownloadScope":
        return DownloadScope(self.download)


class DownloadScope:
    def __init__(self, download: "FakeDownload") -> None:
        self._download = download

    async def __aenter__(self) -> "DownloadScope":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    @property
    def value(self):
        async def resolve() -> "FakeDownload":
            return self._download

        return resolve()


class FakeDownload:
    url = "https://example.com/file.txt"
    suggested_filename = "..\\private report.txt"

    async def path(self) -> str:
        path = Path(tempfile.gettempdir()) / "elysia-test-download.bin"
        path.write_bytes(b"download")
        return str(path)

    async def save_as(self, path: str) -> None:
        Path(path).write_bytes(b"download")


class Phase6BrowserArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        settings = get_settings()
        settings.BROWSER_ALLOWED_DOMAINS = "example.com"
        settings.BROWSER_SCREENSHOT_ROOT = str(Path(self.temp.name) / "screens")
        settings.BROWSER_DOWNLOAD_ROOT = str(Path(self.temp.name) / "downloads")
        settings.BROWSER_SCREENSHOTS_ENABLED = False
        settings.BROWSER_DOWNLOADS_ENABLED = False
        settings.BROWSER_MAX_SCREENSHOT_BYTES = 100
        settings.BROWSER_MAX_DOWNLOAD_BYTES = 100
        browser_manager._sessions.clear()

    def tearDown(self) -> None:
        browser_manager._sessions.clear()
        self.temp.cleanup()

    def _session(self, page: FakePage) -> BrowserSession:
        return BrowserSession(
            session_id="a" * 32,
            context=SimpleNamespace(),
            page=page,
            origin="https://example.com",
            created_at=time.monotonic(),
            last_used_at=time.monotonic(),
            current_url=page.url,
        )

    def test_registry_confirmation_boundary(self) -> None:
        screenshot = asyncio.run(registry.execute("screenshot_browser_page", {"session_id": "a" * 32}))
        download = asyncio.run(
            registry.execute(
                "download_browser_file",
                {"session_id": "a" * 32, "url": "https://example.com/file.txt"},
            )
        )
        self.assertEqual(screenshot.status, "confirmation_required")
        self.assertEqual(download.status, "confirmation_required")

    def test_screenshot_is_disabled_then_bounded(self) -> None:
        page = FakePage(b"visible viewport")
        browser_manager._sessions["a" * 32] = self._session(page)
        with self.assertRaises(BrowserSessionError):
            asyncio.run(browser_manager.screenshot("a" * 32))
        get_settings().BROWSER_SCREENSHOTS_ENABLED = True
        result = asyncio.run(browser_manager.screenshot("a" * 32))
        output = Path(result["path"])
        self.assertTrue(output.is_relative_to(Path(self.temp.name) / "screens"))
        self.assertEqual(output.read_bytes(), b"visible viewport")

    def test_download_is_disabled_then_same_origin_and_safely_named(self) -> None:
        page = FakePage()
        page.download = FakeDownload()
        browser_manager._sessions["a" * 32] = self._session(page)
        with self.assertRaises(BrowserSessionError):
            asyncio.run(browser_manager.download("a" * 32, "https://example.com/file.txt"))
        get_settings().BROWSER_DOWNLOADS_ENABLED = True
        result = asyncio.run(browser_manager.download("a" * 32, "https://example.com/file.txt"))
        output = Path(result["path"])
        self.assertTrue(output.is_relative_to(Path(self.temp.name) / "downloads"))
        self.assertNotIn("\\", result["filename"])
        with self.assertRaises(BrowserSessionError):
            asyncio.run(browser_manager.download("a" * 32, "https://other.example/file.txt"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
