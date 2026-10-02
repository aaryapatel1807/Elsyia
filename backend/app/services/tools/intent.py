"""Fast deterministic intent routing for common Elysia actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class ToolIntent:
    """A routed tool intent extracted without an LLM call."""

    tool_name: str
    arguments: dict[str, Any]
    confidence: float


_OPEN_APP_RE = re.compile(r"^(?:open|launch|start)\s+(.+?)\s*$", re.IGNORECASE)
_SEARCH_FILES_RE = re.compile(
    r"^(?:search|find)\s+(?:for\s+)?(.+?)(?:\s+in\s+(?:my\s+)?files?)?\s*$",
    re.IGNORECASE,
)
_SEARCH_CONTENT_RE = re.compile(
    r"^(?:search|find)\s+(?:my\s+)?files?\s+(?:for|containing)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_SUMMARIZE_RE = re.compile(r"^(?:summari[sz]e|give me a summary of)\s+(.+?)\s*$", re.IGNORECASE)
_DRAFT_RE = re.compile(r"^(?:draft|write a draft|compose)\s+(.+?)\s*$", re.IGNORECASE)
_REMIND_IN_RE = re.compile(
    r"^remind me to\s+(.+?)\s+in\s+(\d+)\s+minutes?$", re.IGNORECASE
)
_REMIND_AT_RE = re.compile(
    r"^remind me to\s+(.+?)\s+at\s+(\d{4}-\d{2}-\d{2}T[^\s]+)$", re.IGNORECASE
)
_CANCEL_REMINDER_RE = re.compile(r"^(?:cancel|delete)\s+reminder\s+(\d+)$", re.IGNORECASE)
_SET_VOLUME_RE = re.compile(r"^(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})\s*%?$", re.IGNORECASE)
_SET_BRIGHTNESS_RE = re.compile(r"^(?:set\s+)?brightness\s+(?:to\s+)?(\d{1,3})\s*%?$", re.IGNORECASE)
_OPEN_SETTINGS_RE = re.compile(r"^(?:open|show)\s+(.+?)\s+settings$", re.IGNORECASE)
_SEARCH_CODE_RE = re.compile(r"^(?:search|find)\s+code\s+(?:for\s+)?(.+)$", re.IGNORECASE)


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def route_intent(message: str) -> ToolIntent | None:
    """Route only high-confidence command patterns; return None for normal chat."""
    text = _clean(message)
    lowered = text.lower()
    phrase = lowered.rstrip(" ?!.")

    if lowered in {"what time is it", "what's the time", "tell me the time", "current time"}:
        return ToolIntent("get_current_time", {}, 0.99)

    if lowered in {"system info", "show system info", "what computer am i using", "computer info"}:
        return ToolIntent("get_system_info", {}, 0.99)

    match = _OPEN_APP_RE.match(text)
    if match and not lowered.endswith(" settings"):
        target = match.group(1).strip(" .")
        if target:
            return ToolIntent("launch_application", {"application": target}, 0.96)

    if phrase in {
        "get world news",
        "what's happening in the world",
        "world news",
        "what is the update today",
        "what's the update today",
        "today's update",
        "daily update",
        "what is happening today",
        "what's happening today",
        "latest world news",
        "today's news",
    }:
        return ToolIntent("get_world_news", {}, 0.96)

    if lowered in {"list reminders", "show reminders", "what are my reminders"}:
        return ToolIntent("list_reminders", {}, 0.98)

    if lowered in {"list windows", "show open windows", "what windows are open"}:
        return ToolIntent("list_windows", {}, 0.96)

    if lowered in {"active window", "what window is active", "which window is active"}:
        return ToolIntent("get_active_window", {}, 0.96)

    if lowered in {"network status", "show network status", "is the network connected"}:
        return ToolIntent("network_status", {}, 0.95)

    if lowered in {"read clipboard", "what is on my clipboard", "show clipboard"}:
        return ToolIntent("read_clipboard", {}, 0.95)

    if lowered in {"analyze repository", "analyze codebase", "analyze this project"}:
        return ToolIntent("analyze_code_repository", {}, 0.95)

    if lowered in {"index repository", "index this project", "build code index"}:
        return ToolIntent("index_code_repository", {}, 0.95)

    match = _SEARCH_CODE_RE.match(text)
    if match:
        return ToolIntent("search_code_repository", {"query": _clean(match.group(1)), "mode": "text"}, 0.95)

    if lowered in {"volume status", "what is the volume", "check volume"}:
        return ToolIntent("get_system_volume", {}, 0.95)

    if lowered in {"brightness status", "what is the brightness", "check brightness"}:
        return ToolIntent("get_display_brightness", {}, 0.95)

    if lowered in {"mute", "mute volume", "mute the computer"}:
        return ToolIntent("set_system_mute", {"muted": True}, 0.96)

    if lowered in {"unmute", "unmute volume", "unmute the computer"}:
        return ToolIntent("set_system_mute", {"muted": False}, 0.96)

    match = _SET_VOLUME_RE.match(text)
    if match:
        return ToolIntent("set_system_volume", {"volume_percent": int(match.group(1))}, 0.96)

    match = _SET_BRIGHTNESS_RE.match(text)
    if match:
        return ToolIntent("set_display_brightness", {"brightness_percent": int(match.group(1))}, 0.96)

    match = _OPEN_SETTINGS_RE.match(text)
    if match:
        page = _clean(match.group(1))
        if page.lower() in {"display", "sound", "network", "bluetooth", "privacy", "windows update", "apps"}:
            return ToolIntent("open_windows_settings", {"page": page}, 0.94)

    match = _CANCEL_REMINDER_RE.match(text)
    if match:
        return ToolIntent("cancel_reminder", {"reminder_id": int(match.group(1))}, 0.98)

    match = _REMIND_IN_RE.match(text)
    if match:
        minutes = int(match.group(2))
        due_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return ToolIntent(
            "create_reminder",
            {"title": _clean(match.group(1)), "due_at": due_at.isoformat()},
            0.97,
        )

    match = _REMIND_AT_RE.match(text)
    if match:
        return ToolIntent(
            "create_reminder",
            {"title": _clean(match.group(1)), "due_at": match.group(2)},
            0.97,
        )

    match = _SEARCH_CONTENT_RE.match(text)
    if match:
        return ToolIntent("search_local_files", {"query": _clean(match.group(1)), "mode": "content"}, 0.94)

    match = _SEARCH_FILES_RE.match(text)
    if match:
        query = _clean(match.group(1)).strip(" .")
        if len(query) >= 2:
            return ToolIntent("search_local_files", {"query": query, "mode": "name"}, 0.92)

    match = _SUMMARIZE_RE.match(text)
    if match:
        path = match.group(1).strip(" .")
        if path:
            return ToolIntent("summarize_local_document", {"path": path}, 0.91)

    match = _DRAFT_RE.match(text)
    if match:
        instruction = _clean(match.group(1)).strip(" .")
        if len(instruction) >= 3:
            return ToolIntent("draft_text", {"instruction": instruction}, 0.91)

    return None
