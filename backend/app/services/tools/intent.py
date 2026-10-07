"""Fast deterministic intent routing for common Elysia actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.tools.timeparse import parse_datetime, parse_duration, words_to_number


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

# --- Jev integration patterns ---
_YOUTUBE_RE = re.compile(r"^play\s+(.+?)\s+on\s+youtube\s*$", re.IGNORECASE)
_SPOTIFY_PLAY_RE = re.compile(r"^play\s+(.+?)\s+on\s+spotify\s*$", re.IGNORECASE)
_SPOTIFY_OPEN_RE = re.compile(r"^open\s+spotify\s*$", re.IGNORECASE)
_MEDIA_RE = re.compile(
    r"^(pause|resume|next|previous|skip)(\s+(the\s+)?(music|song|video|playback|track))?$",
    re.IGNORECASE,
)
_WHATSAPP_RE = re.compile(
    r"^(?:message|text)\s+(.+?)\s+on\s+whatsapp\s+(?:saying\s+)?(.+)$", re.IGNORECASE
)
_WHATSAPP_SHORT_RE = re.compile(r"^whatsapp\s+(\+?[\d][\d\s\-]{6,})\s+(.+)$", re.IGNORECASE)
_LINKEDIN_OPEN_RE = re.compile(r"^open\s+linkedin(?:\s+(jobs|feed))?\s*$", re.IGNORECASE)
_LINKEDIN_SEARCH_RE = re.compile(r"^search\s+linkedin\s+for\s+(.+)$", re.IGNORECASE)
_GMAIL_CHECK_PHRASES = {
    "check my email", "check email", "check my emails", "check my inbox",
    "any new email", "any new emails", "unread emails", "unread email",
    "read my unread emails", "do i have new email", "new emails",
}
_GMAIL_SEARCH_RE = re.compile(r"^search\s+(?:my\s+)?emails?\s+for\s+(.+)$", re.IGNORECASE)
_GMAIL_SEND_RE = re.compile(
    r"^send\s+(?:an?\s+)?email\s+to\s+(\S+@\S+)\s+subject\s+(.+?)\s+(?:saying|body)\s+(.+)$",
    re.IGNORECASE,
)
_CALENDAR_TODAY_PHRASES = {
    "what's on my calendar", "whats on my calendar", "my schedule today",
    "today's schedule", "todays schedule", "what do i have today",
    "what's my schedule", "whats my schedule", "check my calendar",
}
_CALENDAR_CREATE_RE = re.compile(
    r"^(?:schedule|add)(?:\s+an?)?(?:\s+calendar)?(?:\s+event)?\s+(.+?)\s+at\s+"
    r"(\d{4}-\d{2}-\d{2}T[^\s]+)(?:\s+to\s+(\d{4}-\d{2}-\d{2}T[^\s]+))?$",
    re.IGNORECASE,
)
_TIMER_RE = re.compile(
    r"^(?:set\s+)?(?:a\s+)?timer\s+for\s+(.+?)\s*$",
    re.IGNORECASE,
)
_TIMER_LABEL_RE = re.compile(
    r"^(?P<duration>.+?)\s+(?:called|named)\s+(?P<label>.+)$", re.IGNORECASE
)
# Natural-language fallbacks (ISO patterns above keep priority).
# NOTE: group(1) is GREEDY here on purpose — "remind me to check in on
# mom in 5 minutes" must title "check in on mom", not "check".
_REMIND_IN_NATURAL_RE = re.compile(
    r"^remind me to\s+(.+)\s+in\s+(.+)$", re.IGNORECASE
)
_REMIND_AT_NATURAL_RE = re.compile(
    r"^remind me to\s+(.+?)\s+((?:tomorrow|today)\b.*|"
    r"(?:next\s+\w+|(?:on\s+)?(?:mon|tues?|wednes?|thurs?|fri|satur?|sun)(?:day)?s?)\b.*|"
    r"(?:at\s+\d.*))$",
    re.IGNORECASE,
)
_CALENDAR_NATURAL_RE = re.compile(
    r"^(?:schedule|add)(?:\s+an?)?(?:\s+calendar)?(?:\s+event)?\s+(.+?)\s+"
    r"((?:tomorrow|today)\b.*|(?:next\s+\w+\b.*)|"
    r"(?:on\s+(?:mon|tues?|wednes?|thurs?|fri|satur?|sun)(?:day)?s?\b.*)|"
    r"(?:at\s+\d.*))$",
    re.IGNORECASE,
)
_NOTE_RE = re.compile(
    r"^(?:take\s+a\s+note|note\s+down|remember)\s+(?:that\s+)?(.+)$", re.IGNORECASE
)
_NOTES_READ_PHRASES = {"read my notes", "read notes", "show my notes", "show notes"}
_WEATHER_IN_RE = re.compile(
    r"^(?:what(?:'s| is) the weather|how(?:'s| is) the weather|weather)(?:\s+in\s+(.+?)|\s+at\s+(.+?)|\s+for\s+(.+?))?\s*$",
    re.IGNORECASE,
)
_WEATHER_UMBRELLA_PHRASES = {
    "do i need an umbrella", "will it rain today", "is it going to rain",
    "will it rain", "how hot is it", "how cold is it",
}
_SYSTEM_STATS_PHRASES = {
    "system stats", "how is my computer doing", "how is my pc doing",
    "cpu usage", "memory usage", "disk space", "how much disk space",
    "is my computer slow",
}


def _route_jev_intent(text: str, phrase: str, lowered: str) -> ToolIntent | None:
    """Route Jev's app-integration and productivity commands."""
    match = _YOUTUBE_RE.match(text)
    if match:
        return ToolIntent("play_youtube", {"query": _clean(match.group(1))}, 0.97)

    match = _SPOTIFY_PLAY_RE.match(text)
    if match:
        return ToolIntent("open_spotify", {"query": _clean(match.group(1))}, 0.97)
    if _SPOTIFY_OPEN_RE.match(text):
        return ToolIntent("open_spotify", {}, 0.97)

    match = _MEDIA_RE.match(phrase)
    if match:
        return ToolIntent("media_control", {"action": match.group(1).lower()}, 0.97)

    match = _WHATSAPP_RE.match(text)
    if match:
        return ToolIntent(
            "message_whatsapp",
            {"to": _clean(match.group(1)), "text": _clean(match.group(2))},
            0.97,
        )
    match = _WHATSAPP_SHORT_RE.match(text)
    if match:
        return ToolIntent(
            "message_whatsapp",
            {"to": _clean(match.group(1)), "text": _clean(match.group(2))},
            0.97,
        )

    match = _LINKEDIN_OPEN_RE.match(phrase)
    if match:
        target = (match.group(1) or "feed").lower()
        return ToolIntent("open_linkedin", {"target": target}, 0.97)
    match = _LINKEDIN_SEARCH_RE.match(text)
    if match:
        return ToolIntent(
            "open_linkedin", {"target": f"search:{_clean(match.group(1))}"}, 0.97
        )

    if phrase in _GMAIL_CHECK_PHRASES:
        return ToolIntent("check_gmail", {}, 0.97)
    if lowered in {"connect gmail", "connect my gmail"}:
        return ToolIntent("connect_gmail", {}, 0.98)
    match = _GMAIL_SEARCH_RE.match(text)
    if match:
        return ToolIntent("search_gmail", {"query": _clean(match.group(1))}, 0.97)
    match = _GMAIL_SEND_RE.match(text)
    if match:
        return ToolIntent(
            "send_gmail",
            {
                "to": match.group(1).strip(),
                "subject": _clean(match.group(2)),
                "body": _clean(match.group(3)),
            },
            0.97,
        )

    if phrase in _CALENDAR_TODAY_PHRASES:
        return ToolIntent("calendar_today", {}, 0.97)
    if lowered in {"connect calendar", "connect google calendar", "connect my calendar"}:
        return ToolIntent("connect_calendar", {}, 0.98)
    match = _CALENDAR_CREATE_RE.match(text)
    if match:
        args: dict[str, Any] = {
            "title": _clean(match.group(1)),
            "start": match.group(2).strip(),
        }
        if match.group(3):
            args["end"] = match.group(3).strip()
        return ToolIntent("create_calendar_event", args, 0.95)

    match = _TIMER_RE.match(phrase)
    if match:
        tail = match.group(1).strip()
        label = ""
        label_match = _TIMER_LABEL_RE.match(tail)
        if label_match:
            tail = label_match.group("duration").strip()
            label = _clean(label_match.group("label"))
        duration = parse_duration(tail)
        if duration is not None and duration > timedelta(0):
            minutes = max(1, -(-int(duration.total_seconds()) // 60))  # ceil
            if minutes <= 1440:
                args = {"minutes": minutes}
                if label:
                    args["label"] = label
                return ToolIntent("set_timer", args, 0.96)

    # Natural-language reminder: "remind me to stretch in five minutes",
    # "remind me to check in on mom in 2 hours",
    # "remind me to call mom tomorrow at 5pm". ISO patterns keep priority.
    match = _REMIND_IN_NATURAL_RE.match(text)
    if match:
        delta = parse_duration(match.group(2))
        if delta is not None and delta > timedelta(0):
            due_at = datetime.now(timezone.utc) + delta
            return ToolIntent(
                "create_reminder",
                {"title": _clean(match.group(1)), "due_at": due_at.isoformat()},
                0.94,
            )
    match = _REMIND_AT_NATURAL_RE.match(text)
    if match:
        when = parse_datetime(match.group(2))
        if when is not None:
            return ToolIntent(
                "create_reminder",
                {"title": _clean(match.group(1)), "due_at": when.isoformat()},
                0.94,
            )

    # Natural-language calendar event: "schedule dentist tomorrow at 9am".
    match = _CALENDAR_NATURAL_RE.match(text)
    if match:
        start = parse_datetime(match.group(2))
        if start is not None:
            return ToolIntent(
                "create_calendar_event",
                {"title": _clean(match.group(1)), "start": start.isoformat()},
                0.93,
            )

    match = _NOTE_RE.match(text)
    if match:
        return ToolIntent("take_note", {"text": _clean(match.group(1))}, 0.96)
    if phrase in _NOTES_READ_PHRASES:
        return ToolIntent("read_notes", {}, 0.97)

    return None


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def route_intent(message: str) -> ToolIntent | None:
    """Route only high-confidence command patterns; return None for normal chat."""
    text = _clean(message)
    lowered = text.lower()
    phrase = lowered.rstrip(" ?!.")

    if lowered in {"what time is it", "what's the time", "tell me the time", "current time"}:
        return ToolIntent("get_current_time", {}, 0.99)

    match = _WEATHER_IN_RE.match(phrase)
    if match:
        location = next((g for g in match.groups() if g), "")
        return ToolIntent("get_weather", {"location": _clean(location)}, 0.96)
    if phrase in _WEATHER_UMBRELLA_PHRASES:
        return ToolIntent("get_weather", {}, 0.94)

    if phrase in _SYSTEM_STATS_PHRASES:
        return ToolIntent("get_system_stats", {}, 0.95)

    if lowered in {"system info", "show system info", "what computer am i using", "computer info"}:
        return ToolIntent("get_system_info", {}, 0.99)

    # === Jev integrations (checked before the generic "open X" rule) ===
    routed = _route_jev_intent(text, phrase, lowered)
    if routed is not None:
        return routed

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

    return _fuzzy_route(lowered)


# --- Fuzzy fallback: near-miss phrasings ---------------------------------
# When no regex or phrase matches, score the utterance against canonical
# command phrases by token overlap. Deliberately conservative: it only
# fires for short command-like utterances with strong overlap, and always
# loses to every regex above.

_FUZZY_COMMANDS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("check my email", "check_gmail", {}),
    ("check my inbox", "check_gmail", {}),
    ("any new email", "check_gmail", {}),
    ("read my unread emails", "check_gmail", {}),
    ("what is on my calendar", "calendar_today", {}),
    ("my schedule today", "calendar_today", {}),
    ("check my calendar", "calendar_today", {}),
    ("read my notes", "read_notes", {}),
    ("show my notes", "read_notes", {}),
    ("list my reminders", "list_reminders", {}),
    ("show my reminders", "list_reminders", {}),
    ("what is the time", "get_current_time", {}),
    ("tell me the time", "get_current_time", {}),
    ("what is the date today", "get_current_date", {}),
    ("pause the music", "media_control", {"action": "pause"}),
    ("resume the music", "media_control", {"action": "resume"}),
    ("skip this song", "media_control", {"action": "next"}),
    ("next track", "media_control", {"action": "next"}),
    ("read my clipboard", "read_clipboard", {}),
    ("what is on my clipboard", "read_clipboard", {}),
    ("is the network connected", "network_status", {}),
    ("check network status", "network_status", {}),
    ("mute the volume", "set_system_mute", {"muted": True}),
    ("unmute the volume", "set_system_mute", {"muted": False}),
    ("open youtube", "play_youtube", {"query": ""}),
    ("connect my gmail", "connect_gmail", {}),
    ("connect my calendar", "connect_calendar", {}),
)

_STOPWORDS = frozenset({
    "the", "a", "an", "my", "me", "please", "kindly", "just", "now",
    "hey", "jev", "could", "would", "can", "you", "it", "is", "are",
})


def _fuzzy_route(lowered: str) -> ToolIntent | None:
    """Token-overlap fallback for near-miss command phrasings."""
    words = [w for w in re.findall(r"[a-z']+", lowered) if w not in _STOPWORDS]
    if not words or len(words) > 12:
        return None
    word_set = set(words)
    best: tuple[float, str, dict[str, Any]] | None = None
    for phrase, tool, args in _FUZZY_COMMANDS:
        phrase_words = [w for w in phrase.split() if w not in _STOPWORDS]
        if not phrase_words:
            continue
        overlap = len(word_set & set(phrase_words)) / len(phrase_words)
        # Require most of the canonical phrase present, in any order.
        if overlap >= 0.75 and len(word_set & set(phrase_words)) >= 2:
            score = overlap
            if best is None or score > best[0]:
                best = (score, tool, args)
    if best is None:
        return None
    _, tool, args = best
    return ToolIntent(tool, dict(args), 0.72)
