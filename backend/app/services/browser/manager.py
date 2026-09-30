"""Isolated Playwright session manager for the browser foundation."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from app.core import get_settings
from app.services.browser.policy import BrowserPolicyError, ValidatedUrl, validate_final_url, validate_url


class BrowserSessionError(Exception):
    """Expected browser session or extraction failure."""


@dataclass
class BrowserSession:
    session_id: str
    context: Any
    page: Any
    origin: str
    created_at: float
    last_used_at: float
    state: str = "active"
    current_url: str = ""
    title: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "origin": self.origin,
            "current_url": self.current_url,
            "title": self.title,
            "state": self.state,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }


class BrowserSessionManager:
    """Own browser lifecycle and ensure no persistent cookie state is retained."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Any:
        if self._browser is not None:
            return self._browser
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=get_settings().BROWSER_HEADLESS,
            )
            return self._browser
        except Exception as exc:
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
            raise BrowserSessionError("The local Chromium browser runtime is unavailable.") from exc

    async def _cleanup_expired_locked(self) -> None:
        now = time.monotonic()
        settings = get_settings()
        expired: list[str] = []
        for session_id, session in self._sessions.items():
            idle = now - session.last_used_at > settings.BROWSER_SESSION_IDLE_SECONDS
            lifetime = now - session.created_at > settings.BROWSER_SESSION_MAX_SECONDS
            if idle or lifetime:
                expired.append(session_id)
        for session_id in expired:
            await self._close_locked(session_id, state="expired")

    async def create_and_navigate(self, raw_url: str) -> BrowserSession:
        """Create a fresh isolated context and navigate to a trusted URL."""
        validated = validate_url(raw_url)
        async with self._lock:
            await self._cleanup_expired_locked()
            if len(self._sessions) >= get_settings().BROWSER_MAX_SESSIONS:
                raise BrowserSessionError("Maximum browser session count reached.")
            browser = await self._ensure_browser()
            context: Any | None = None
            try:
                context = await browser.new_context(
                    accept_downloads=False,
                    service_workers="block",
                    java_script_enabled=True,
                    ignore_https_errors=False,
                )
                page = await context.new_page()
                page.set_default_timeout(get_settings().BROWSER_ACTION_TIMEOUT_SECONDS * 1000)
                page.set_default_navigation_timeout(get_settings().BROWSER_NAVIGATION_TIMEOUT_SECONDS * 1000)
                response = await page.goto(validated.url, wait_until="domcontentloaded")
                final = validate_final_url(page.url, validated.origin)
                session_id = uuid.uuid4().hex
                now = time.monotonic()
                session = BrowserSession(
                    session_id=session_id,
                    context=context,
                    page=page,
                    origin=final.origin,
                    created_at=now,
                    last_used_at=now,
                    current_url=final.url,
                    title=await page.title(),
                )
                self._sessions[session_id] = session
                return session
            except BrowserPolicyError:
                await context.close()
                raise
            except Exception as exc:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                raise BrowserSessionError("Browser navigation failed or timed out.") from exc

    async def get(self, session_id: str) -> BrowserSession:
        async with self._lock:
            await self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None or session.state != "active":
                raise BrowserSessionError("Browser session is not active.")
            session.last_used_at = time.monotonic()
            return session

    async def scrape(self, session_id: str) -> dict[str, Any]:
        session = await self.get(session_id)
        settings = get_settings()
        try:
            title = await session.page.title()
            text = await session.page.locator("body").inner_text(timeout=settings.BROWSER_ACTION_TIMEOUT_SECONDS * 1000)
            headings = await session.page.locator("h1, h2, h3").all_text_contents()
            links = await session.page.locator("a[href]").evaluate_all(
                "elements => elements.map(element => ({text: element.innerText, href: element.href}))"
            )
            rows = await session.page.locator("table tr").all_text_contents()
        except Exception as exc:
            raise BrowserSessionError("Page extraction failed or timed out.") from exc
        session.last_used_at = time.monotonic()
        session.current_url = session.page.url
        session.title = title
        bounded_text = text[: settings.BROWSER_MAX_TEXT_CHARS]
        bounded_headings = [" ".join(item.split()) for item in headings[: settings.BROWSER_MAX_HEADINGS] if item.strip()]
        bounded_links = [
            {"text": " ".join(str(item.get("text", "")).split())[:300], "href": str(item.get("href", ""))[:2048]}
            for item in links[: settings.BROWSER_MAX_LINKS]
            if isinstance(item, dict) and item.get("href")
        ]
        bounded_rows = [" ".join(row.split())[:1000] for row in rows[: settings.BROWSER_MAX_TABLE_ROWS] if row.strip()]
        return {
            "session_id": session.session_id,
            "url": session.current_url,
            "title": title,
            "text": bounded_text,
            "text_truncated": len(text) > len(bounded_text),
            "headings": bounded_headings,
            "links": bounded_links,
            "table_rows": bounded_rows,
        }

    def _artifact_root(self, configured: str) -> Path:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            root = Path(__file__).parents[4] / root
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    async def screenshot(self, session_id: str) -> dict[str, Any]:
        """Capture only the visible browser viewport into a controlled local root."""
        session = await self.get(session_id)
        settings = get_settings()
        if not settings.BROWSER_SCREENSHOTS_ENABLED:
            raise BrowserSessionError("Browser screenshots are disabled by configuration.")
        root = self._artifact_root(settings.BROWSER_SCREENSHOT_ROOT)
        output = root / f"browser-{session.session_id}-{uuid.uuid4().hex}.png"
        try:
            await session.page.screenshot(
                path=str(output),
                type="png",
                full_page=False,
                timeout=settings.BROWSER_ACTION_TIMEOUT_SECONDS * 1000,
            )
        except Exception as exc:
            output.unlink(missing_ok=True)
            raise BrowserSessionError("Visible browser screenshot failed or timed out.") from exc
        try:
            size = output.stat().st_size
        except OSError as exc:
            raise BrowserSessionError("Browser screenshot was not saved locally.") from exc
        if size > settings.BROWSER_MAX_SCREENSHOT_BYTES:
            output.unlink(missing_ok=True)
            raise BrowserSessionError("Browser screenshot exceeded the configured size limit.")
        session.last_used_at = time.monotonic()
        return {
            "session_id": session.session_id,
            "path": str(output),
            "bytes": size,
            "url": session.page.url,
            "status": "captured",
        }

    async def download(self, session_id: str, raw_url: str) -> dict[str, Any]:
        """Download one same-origin file into a bounded local browser root."""
        session = await self.get(session_id)
        settings = get_settings()
        if not settings.BROWSER_DOWNLOADS_ENABLED:
            raise BrowserSessionError("Browser downloads are disabled by configuration.")
        try:
            validated = validate_url(raw_url)
            if validated.origin != session.origin:
                raise BrowserSessionError("Browser downloads must remain on the active session origin.")
            root = self._artifact_root(settings.BROWSER_DOWNLOAD_ROOT)
            async with session.page.expect_download(
                timeout=settings.BROWSER_ACTION_TIMEOUT_SECONDS * 1000
            ) as download_info:
                await session.page.goto(validated.url, wait_until="commit")
            download = await download_info.value
            final = validate_final_url(download.url, session.origin)
            temporary = await download.path()
            if temporary is None:
                raise BrowserSessionError("Browser did not expose a local download stream.")
            size = Path(temporary).stat().st_size
            if size > settings.BROWSER_MAX_DOWNLOAD_BYTES:
                raise BrowserSessionError("Browser download exceeded the configured size limit.")
            suggested = Path(download.suggested_filename or "download.bin").name
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", suggested)[:120] or "download.bin"
            output = root / f"{uuid.uuid4().hex}-{safe_name}"
            await download.save_as(str(output))
            session.last_used_at = time.monotonic()
            session.current_url = final.url
            return {
                "session_id": session.session_id,
                "path": str(output),
                "filename": safe_name,
                "bytes": size,
                "url": final.url,
                "status": "downloaded",
            }
        except BrowserPolicyError as exc:
            raise BrowserSessionError(str(exc)) from exc
        except BrowserSessionError:
            raise
        except Exception as exc:
            raise BrowserSessionError("Browser download failed or timed out.") from exc

    async def _close_locked(self, session_id: str, *, state: str = "closed") -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.state = state
        try:
            await session.context.close()
        except Exception:
            pass
        return True

    async def close(self, session_id: str) -> bool:
        async with self._lock:
            return await self._close_locked(session_id)

    async def close_all(self) -> None:
        async with self._lock:
            for session_id in list(self._sessions):
                await self._close_locked(session_id)
            if self._browser is not None:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

    def list_sessions(self) -> list[dict[str, Any]]:
        return [session.as_dict() for session in self._sessions.values()]


browser_manager = BrowserSessionManager()
