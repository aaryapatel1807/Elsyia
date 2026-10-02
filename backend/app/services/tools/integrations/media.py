"""Media and messaging integrations: YouTube, WhatsApp, LinkedIn, Spotify."""

from __future__ import annotations

import asyncio
import platform
from typing import Any
from urllib.parse import quote_plus

from app.core import get_logger, get_settings
from app.services.jev.contacts import resolve_contact
from app.services.jev.open import open_url
from app.services.tools.base import Tool, ToolError

logger = get_logger(__name__)

# Virtual-key codes for system media keys (Windows).
_MEDIA_KEYS = {
    "play_pause": 0xB3,  # VK_MEDIA_PLAY_PAUSE
    "next": 0xB0,  # VK_MEDIA_NEXT_TRACK
    "previous": 0xB1,  # VK_MEDIA_PREV_TRACK
}


async def press_media_key(action: str) -> None:
    """Press a system media key on Windows; honest error elsewhere."""
    virtual_key = _MEDIA_KEYS.get(action)
    if virtual_key is None:
        raise ToolError(f"Unknown media action '{action}'.")
    if platform.system() != "Windows":
        raise ToolError(
            "Media-key control is supported on Windows only on this machine."
        )
    settings = get_settings()
    if not getattr(settings, "DESKTOP_INPUT_ENABLED", False):
        raise ToolError(
            "Input automation is disabled. Set DESKTOP_INPUT_ENABLED=true to opt in."
        )
    import ctypes

    user32 = ctypes.windll.user32
    await asyncio.to_thread(user32.keybd_event, virtual_key, 0, 0, 0)
    await asyncio.to_thread(user32.keybd_event, virtual_key, 0, 2, 0)


def youtube_search_url(query: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def youtube_watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


async def resolve_youtube_video(query: str) -> tuple[str, str] | None:
    """Use the free YouTube Data API to find the top result.

    Returns (video_id, title) or None when no API key is configured.
    Costs 100 quota units per call out of the free 10,000/day.
    """
    api_key = (getattr(get_settings(), "YOUTUBE_API_KEY", "") or "").strip()
    if not api_key:
        return None

    def _call() -> tuple[str, str] | None:
        from googleapiclient.discovery import build

        service = build("youtube", "v3", developerKey=api_key)
        response = (
            service.search()
            .list(q=query, part="snippet", type="video", maxResults=1)
            .execute()
        )
        items = response.get("items", [])
        if not items:
            return None
        return items[0]["id"]["videoId"], items[0]["snippet"]["title"]

    return await asyncio.to_thread(_call)


class PlayYouTubeTool(Tool):
    name = "play_youtube"
    description = (
        "Play a video on YouTube. With a free YouTube Data API key "
        "configured, opens the exact top result; otherwise opens the "
        "YouTube search page for the query."
    )

    async def run(self, query: str) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise ToolError("Tell me what to play on YouTube.")
        resolved = await resolve_youtube_video(query)
        if resolved:
            video_id, title = resolved
            url = youtube_watch_url(video_id)
            await open_url(url)
            return {"url": url, "title": title, "mode": "exact_video"}
        url = youtube_search_url(query)
        await open_url(url)
        return {"url": url, "query": query, "mode": "search"}


class MediaControlTool(Tool):
    name = "media_control"
    description = (
        "Control media playback with system media keys: play_pause, next, "
        "or previous. Works with YouTube, Spotify, or any media app that "
        "listens for media keys. Windows only; needs DESKTOP_INPUT_ENABLED."
    )

    async def run(self, action: str) -> dict[str, str]:
        normalized = (action or "").strip().lower().replace(" ", "_")
        aliases = {
            "play": "play_pause",
            "pause": "play_pause",
            "resume": "play_pause",
            "toggle": "play_pause",
            "skip": "next",
            "forward": "next",
            "back": "previous",
        }
        resolved = aliases.get(normalized, normalized)
        await press_media_key(resolved)
        return {"action": resolved, "status": "sent"}


def whatsapp_url(number: str, text: str) -> str:
    return f"https://wa.me/{number}?text={quote_plus(text)}"


class MessageWhatsAppTool(Tool):
    name = "message_whatsapp"
    description = (
        "Open a WhatsApp chat with prefilled text, ready to send. "
        "'to' is a name from ~/.jev/contacts.json or a phone number in "
        "international format. Opens the chat in WhatsApp Web/desktop — "
        "Aarya taps send himself, which is the honest limit of the free "
        "platform: there is no official API for personal WhatsApp sending."
    )

    async def run(self, to: str, text: str) -> dict[str, str]:
        if not (to or "").strip():
            raise ToolError("Tell me who to message on WhatsApp.")
        if not (text or "").strip():
            raise ToolError("Tell me what the message should say.")
        number = resolve_contact(to)
        url = whatsapp_url(number, text.strip())
        await open_url(url)
        return {
            "to": to.strip(),
            "number": number,
            "url": url,
            "status": "chat_opened_prefilled",
            "note": "Review the text and press send in WhatsApp.",
        }


def linkedin_url(target: str) -> str:
    normalized = (target or "feed").strip().lower()
    if normalized.startswith("search:"):
        query = normalized.split("search:", 1)[1].strip()
        return f"https://www.linkedin.com/search/results/all/?keywords={quote_plus(query)}"
    if normalized.startswith("profile:"):
        handle = normalized.split("profile:", 1)[1].strip().strip("/")
        if handle.startswith("http"):
            return handle
        return f"https://www.linkedin.com/in/{quote_plus(handle)}"
    if normalized in {"jobs", "job"}:
        return "https://www.linkedin.com/jobs/"
    return "https://www.linkedin.com/feed/"


class OpenLinkedInTool(Tool):
    name = "open_linkedin"
    description = (
        "Open LinkedIn: the feed, jobs, a keyword search "
        "('search:data science internships'), or a profile "
        "('profile:aaryapatel'). Posting is not available — LinkedIn only "
        "offers posting to approved partners, so Jev opens the share "
        "composer URL instead of faking an API post."
    )

    async def run(self, target: str = "feed") -> dict[str, str]:
        url = linkedin_url(target)
        await open_url(url)
        return {"url": url, "target": (target or "feed").strip()}


class OpenSpotifyTool(Tool):
    name = "open_spotify"
    description = (
        "Open Spotify in the browser: home, or a search for an artist, "
        "song, or playlist. Playback itself is controlled with the "
        "media_control tool."
    )

    async def run(self, query: str = "") -> dict[str, str]:
        query = (query or "").strip()
        url = (
            f"https://open.spotify.com/search/{quote_plus(query)}"
            if query
            else "https://open.spotify.com/"
        )
        await open_url(url)
        return {"url": url, "query": query}
