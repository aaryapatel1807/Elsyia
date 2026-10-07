"""Natural-language time parsing for voice commands.

Voice users can't speak ISO-8601, so the intent router needs to understand
phrases like "in 5 minutes", "tomorrow at 5pm", "next monday at 9am" or
"at 7:30". Pure stdlib — no new dependencies.

Public API:
    parse_duration(text)  -> timedelta | None   ("5 minutes", "2 hours", ...)
    parse_datetime(text, now=None) -> datetime | None  (absolute future moment)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_NUMBER_WORDS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "hundred": 100,
    "a": 1, "an": 1, "half": 0,  # "half an hour" handled specially
}

_WEEKDAYS: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_DURATION_RE = re.compile(
    r"(?P<num>\d+|[a-z]+(?:\s+[a-z]+)?)\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b",
    re.IGNORECASE,
)

_TIME_OF_DAY_RE = re.compile(
    r"\b(?:at\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>[ap]\.?m\.?)?\b",
    re.IGNORECASE,
)


def words_to_number(text: str) -> int | None:
    """Convert 'five', 'twenty two', 'a' -> int. Returns None when not a number."""
    text = text.strip().lower()
    if text.isdigit():
        return int(text)
    parts = text.split()
    total = 0
    current = 0
    for part in parts:
        value = _NUMBER_WORDS.get(part)
        if value is None:
            return None
        if part == "hundred":
            current = max(current, 1) * 100
        else:
            current += value
    total += current
    return total if total or text in ("zero", "a", "an") else None


def parse_duration(text: str) -> timedelta | None:
    """Parse '5 minutes', 'two hours', 'half an hour', '90 secs' -> timedelta."""
    lowered = text.strip().lower()
    if re.search(r"\bhalf\s+an?\s+hour\b", lowered):
        return timedelta(minutes=30)
    match = _DURATION_RE.search(lowered)
    if not match:
        return None
    num = words_to_number(match.group("num"))
    if num is None or num < 0:
        return None
    unit = match.group("unit").lower()
    if unit.startswith("sec"):
        return timedelta(seconds=num)
    if unit.startswith("min"):
        return timedelta(minutes=num)
    if unit.startswith("hour") or unit.startswith("hr"):
        return timedelta(hours=num)
    if unit.startswith("day"):
        return timedelta(days=num)
    return None


_MERIDIEM_RE = re.compile(r"\b[ap]\.?m\.?\b", re.IGNORECASE)


def _has_meridiem(text: str) -> bool:
    return bool(_MERIDIEM_RE.search(text))


def _apply_time_of_day(base: datetime, text: str) -> datetime | None:
    """Find 'at 5pm' / '7:30' inside text and set it on base. None if absent."""
    match = _TIME_OF_DAY_RE.search(text)
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    meridiem = (match.group("meridiem") or "").lower().replace(".", "")
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    try:
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None


def parse_datetime(text: str, now: datetime | None = None) -> datetime | None:
    """Parse a future moment from natural language.

    Handles: "in 5 minutes", "in 2 hours", "tomorrow at 5pm", "today at 7:30",
    "next monday at 9am", "monday at 9", "at 7pm". Returns a timezone-aware
    datetime in the caller's local zone, or None when nothing parses.

    Ambiguous bare times ("at 7") resolve to the next occurrence: if 7am
    already passed today, it means 7pm... no — it means 7:00 next: we pick
    the next future occurrence, preferring the literal hour.
    """
    base = now or datetime.now().astimezone()
    lowered = text.strip().lower()

    # "in <duration>" — pure offset from now.
    in_match = re.search(r"\bin\s+(.+)$", lowered)
    if in_match:
        delta = parse_duration(in_match.group(1))
        if delta is not None and delta > timedelta(0):
            return base + delta

    # Day anchors.
    day_offset: int | None = None
    if re.search(r"\btomorrow\b", lowered):
        day_offset = 1
    elif re.search(r"\btoday\b", lowered):
        day_offset = 0
    else:
        weekday_match = re.search(
            r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            lowered,
        )
        if weekday_match:
            target = _WEEKDAYS[weekday_match.group(1)]
            delta_days = (target - base.weekday()) % 7
            day_offset = delta_days if delta_days else 7
        else:
            bare_weekday = re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                lowered,
            )
            if bare_weekday:
                target = _WEEKDAYS[bare_weekday.group(1)]
                delta_days = (target - base.weekday()) % 7
                day_offset = delta_days if delta_days else 7

    if day_offset is not None:
        day = (base + timedelta(days=day_offset)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        timed = _apply_time_of_day(day, lowered)
        result = timed or day
        if result <= base:
            # "today at 7:30" said at 10:00 with no am/pm almost always
            # means 19:30 today — try +12h before rolling to tomorrow.
            if timed is not None and day_offset == 0 and not _has_meridiem(lowered):
                shifted = result + timedelta(hours=12)
                if shifted > base:
                    return shifted
            return result + timedelta(days=1)
        return result

    # Bare "at 7pm" / "7:30" with no day anchor: next future occurrence.
    if re.search(r"\bat\b", lowered) or _TIME_OF_DAY_RE.search(lowered):
        candidate = _apply_time_of_day(base, lowered)
        if candidate is not None:
            if candidate <= base:
                candidate += timedelta(days=1)
            return candidate

    return None
