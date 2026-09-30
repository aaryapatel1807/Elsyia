"""Browser foundation tools backed by the isolated Playwright session manager."""

from __future__ import annotations

from typing import Any

from app.services.browser import BrowserSessionError, browser_manager
from app.services.tools.base import Tool, ToolError


class NavigateBrowserTool(Tool):
    name = "navigate_browser"
    description = "Open an isolated browser session on a configured trusted domain. Read-only foundation action."

    async def run(self, url: str) -> dict[str, Any]:
        try:
            session = await browser_manager.create_and_navigate(url)
        except Exception as exc:
            if isinstance(exc, (ToolError, BrowserSessionError)):
                raise ToolError(str(exc)) from exc
            raise ToolError("Browser navigation was blocked or failed.") from exc
        return {"session": session.as_dict(), "status": "navigated"}


class BrowserSessionInfoTool(Tool):
    name = "browser_session_info"
    description = "Read metadata for an active isolated browser session."

    async def run(self, session_id: str) -> dict[str, Any]:
        try:
            session = await browser_manager.get(session_id)
        except BrowserSessionError as exc:
            raise ToolError(str(exc)) from exc
        return {"session": session.as_dict()}


class ScrapeBrowserPageTool(Tool):
    name = "scrape_browser_page"
    description = "Extract bounded visible text, headings, links, and table rows from an active browser page."

    async def run(self, session_id: str) -> dict[str, Any]:
        try:
            return await browser_manager.scrape(session_id)
        except BrowserSessionError as exc:
            raise ToolError(str(exc)) from exc


class ScreenshotBrowserPageTool(Tool):
    name = "screenshot_browser_page"
    description = "Capture the visible browser viewport into the guarded local screenshot directory; requires confirmation."

    async def run(self, session_id: str) -> dict[str, Any]:
        try:
            return await browser_manager.screenshot(session_id)
        except BrowserSessionError as exc:
            raise ToolError(str(exc)) from exc


class DownloadBrowserFileTool(Tool):
    name = "download_browser_file"
    description = "Download one same-origin browser file into the guarded local download directory; requires confirmation."

    async def run(self, session_id: str, url: str) -> dict[str, Any]:
        try:
            return await browser_manager.download(session_id, url)
        except BrowserSessionError as exc:
            raise ToolError(str(exc)) from exc


class CloseBrowserSessionTool(Tool):
    name = "close_browser_session"
    description = "Close an active isolated browser session and discard its temporary storage."

    async def run(self, session_id: str) -> dict[str, Any]:
        closed = await browser_manager.close(session_id)
        if not closed:
            raise ToolError("Browser session was not found.")
        return {"session_id": session_id, "status": "closed"}
