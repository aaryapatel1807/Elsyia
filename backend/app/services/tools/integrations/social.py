"""Instagram integrations for Elsyia — real, free, ToS-safe.

The Instagram connector (instagram-cli, linked via Meta Accounts Center)
is the real path: Elsyia can list recent reels and describe any reel via
media-understanding. When the CLI is unavailable (e.g. inside the frozen
desktop build where it isn't on PATH), the tools fall back to opening
instagram.com deep links — documented, not faked.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any

from app.core import get_logger
from app.services.elsyia.open import open_url
from app.services.tools.base import Tool, ToolError

logger = get_logger("elsyia.tools.social")

_CLI_TIMEOUT_S = 30
_account_cache: str | None = None


def _cli_path() -> str | None:
    return shutil.which("instagram-cli")


async def _run_cli(*args: str) -> dict[str, Any]:
    """Run instagram-cli and return its parsed JSON output."""
    cli = _cli_path()
    if cli is None:
        raise ToolError("instagram-cli is not installed on this machine.")
    try:
        proc = await asyncio.create_subprocess_exec(
            cli,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_CLI_TIMEOUT_S
        )
    except asyncio.TimeoutError as exc:
        raise ToolError("Instagram request timed out.") from exc
    if proc.returncode != 0:
        detail = (stderr or b"").decode(errors="replace").strip()[:300]
        raise ToolError(f"Instagram request failed: {detail or 'unknown error'}")
    try:
        return json.loads((stdout or b"").decode())
    except json.JSONDecodeError as exc:
        raise ToolError("Instagram returned an unreadable response.") from exc


async def _account_id() -> str:
    """Resolve the linked Instagram account id (cached per process)."""
    global _account_cache
    if _account_cache:
        return _account_cache
    data = await _run_cli("accounts")
    accounts = data.get("accounts") or []
    if not accounts or not accounts[0].get("user_fbid"):
        raise ToolError(
            "No Instagram account is linked. Link one in Meta Accounts Center first."
        )
    _account_cache = str(accounts[0]["user_fbid"])
    return _account_cache


def _reel_summary(post: dict[str, Any]) -> dict[str, str]:
    caption = (post.get("post_caption") or "").strip().replace("\n", " ")
    return {
        "username": str(post.get("username") or ""),
        "caption": caption[:160],
        "url": str(post.get("url") or ""),
    }


class ShowInstagramReelsTool(Tool):
    name = "show_instagram_reels"
    description = (
        "Show recent Instagram reels. With no query, lists your own recent "
        "reels; with a query, filters your recent reels and following feed "
        "for matching captions. Opens the top match. Needs a linked "
        "Instagram account; otherwise opens instagram.com reels."
    )

    async def _own_reels(self, account_id: str, query: str) -> list[dict[str, str]]:
        data = await _run_cli(
            "posts",
            "--account-id",
            account_id,
            "--post-types",
            "REEL",
            "--limit",
            "12",
        )
        reels = data.get("posts") or []
        if query:
            q = query.lower()
            reels = [
                p
                for p in reels
                if q in (p.get("post_caption") or "").lower()
                or q in (p.get("username") or "").lower()
            ]
        return [_reel_summary(p) for p in reels if p.get("url")]

    async def _feed_reels(self, account_id: str, query: str) -> list[dict[str, str]]:
        """Reels from the following feed (media_type video), URLs resolved."""
        data = await _run_cli(
            "feed", "--account-id", account_id, "--variant", "following", "--limit", "25"
        )
        posts = [p for p in (data.get("posts") or []) if p.get("media_type") == "video"]
        if query:
            q = query.lower()
            posts = [
                p
                for p in posts
                if q in (p.get("post_caption") or "").lower()
                or q in (p.get("username") or "").lower()
            ]
        items: list[dict[str, str]] = []
        for post in posts[:3]:  # bounded: resolving permalinks costs one call each
            post_id = post.get("post_id")
            if not post_id:
                continue
            try:
                detail = await _run_cli(
                    "post", "--account-id", account_id, "--id", str(post_id)
                )
                resolved = (detail.get("posts") or [{}])[0]
                if resolved.get("url"):
                    items.append(_reel_summary(resolved))
            except ToolError:
                continue
        return items

    async def run(self, query: str = "") -> dict[str, Any]:
        query = (query or "").strip()
        try:
            account_id = await _account_id()
            items = await self._own_reels(account_id, query)
            source = "your reels"
            if not items:
                items = await self._feed_reels(account_id, query)
                source = "your following feed"
            items = items[:8]
            if not items:
                await open_url("https://www.instagram.com/reels/")
                return {
                    "mode": "browser",
                    "url": "https://www.instagram.com/reels/",
                    "reels": [],
                    "note": (
                        "No matching reels found via the connector — "
                        "opened the reels feed instead."
                    ),
                }
            await open_url(items[0]["url"])
            return {
                "mode": "connector",
                "source": source,
                "reels": items,
                "opened": items[0]["url"],
            }
        except ToolError:
            # CLI missing or account unlinked: honest browser fallback.
            await open_url("https://www.instagram.com/reels/")
            return {
                "mode": "browser",
                "url": "https://www.instagram.com/reels/",
                "reels": [],
                "note": "Connector unavailable — opened the reels feed instead.",
            }


class DescribeInstagramReelTool(Tool):
    name = "describe_instagram_reel"
    description = (
        "Describe what is in an Instagram reel: pass the reel's URL and "
        "Elsyia fetches Instagram's own media understanding summary. "
        "Needs a linked Instagram account; otherwise just opens the URL."
    )

    async def run(self, url: str) -> dict[str, Any]:
        url = (url or "").strip()
        if not url or "instagram.com" not in url:
            raise ToolError("Give me an Instagram reel URL to describe.")
        try:
            account_id = await _account_id()
            post_data = await _run_cli("post", "--account-id", account_id, "--url", url)
            posts = post_data.get("posts") or []
            if not posts:
                raise ToolError("Couldn't read that reel.")
            media_id = str(posts[0].get("post_id") or "")
            if not media_id:
                raise ToolError("Couldn't read that reel.")
            understanding = await _run_cli(
                "media-understanding",
                "--account-id",
                account_id,
                "--media-ids",
                media_id,
            )
            # Shape varies by provider; dig out the first text summary found.
            summary = _extract_summary(understanding)
            caption = (posts[0].get("post_caption") or "").strip()[:300]
            return {
                "url": url,
                "username": str(posts[0].get("username") or ""),
                "caption": caption,
                "summary": summary or "Instagram didn't return a description.",
            }
        except ToolError:
            await open_url(url)
            return {
                "url": url,
                "summary": "",
                "note": "Connector unavailable — opened the reel instead.",
            }


def _extract_summary(data: Any) -> str:
    """Best-effort hunt for a narrative summary in media-understanding output."""
    if isinstance(data, dict):
        for key in (
            "narrative_summary",
            "semantic_understanding",
            "summary",
            "narrative",
            "description",
            "text",
        ):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:800]
        for value in data.values():
            found = _extract_summary(value)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _extract_summary(value)
            if found:
                return found
    return ""
