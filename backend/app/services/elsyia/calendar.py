"""Google Calendar integration for Elsyia — official Calendar API.

Same user-authorises-on-first-run OAuth pattern as Gmail (see oauth.py).
Capabilities: read today's agenda, create events. Nothing is created in
Aarya's Google account during development.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from typing import Any

from app.core import get_logger
from app.services.elsyia.oauth import GoogleOAuth
from app.services.tools.base import Tool, ToolError

logger = get_logger(__name__)

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def calendar_oauth() -> GoogleOAuth:
    return GoogleOAuth(service="calendar", scopes=CALENDAR_SCOPES)


def _service():
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=calendar_oauth().credentials())


def _summarize(event: dict[str, Any]) -> dict[str, str]:
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id", ""),
        "title": event.get("summary", "(no title)"),
        "start": start.get("dateTime", start.get("date", "")),
        "end": end.get("dateTime", end.get("date", "")),
        "location": event.get("location", ""),
    }


class CalendarClient:
    """Thin async wrapper over the official Google Calendar API."""

    async def today(self) -> list[dict[str, str]]:
        def _call():
            now = datetime.now(timezone.utc)
            start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
            end = datetime.combine(now.date(), time.max, tzinfo=timezone.utc)
            response = (
                _service()
                .events()
                .list(
                    calendarId="primary",
                    timeMin=start.isoformat(),
                    timeMax=end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            return [_summarize(e) for e in response.get("items", [])]

        return await asyncio.to_thread(_call)

    async def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str = "",
        description: str = "",
    ) -> dict[str, str]:
        def _call():
            body: dict[str, Any] = {"summary": title, "start": {"dateTime": start_iso}}
            if end_iso:
                body["end"] = {"dateTime": end_iso}
            if description:
                body["description"] = description
            created = (
                _service().events().insert(calendarId="primary", body=body).execute()
            )
            return _summarize(created)

        return await asyncio.to_thread(_call)


def _require_connected() -> None:
    if not calendar_oauth().is_authorized():
        raise ToolError(
            "Google Calendar is not connected yet. Say 'Elsyia, connect calendar' "
            "and I will open Google's sign-in page for you to authorise it."
        )


def _parse_iso(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ToolError("A start date/time is required in ISO-8601 format.")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(
            "Date/time must be ISO-8601, e.g. 2026-10-03T15:30:00+05:30."
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


class CalendarTodayTool(Tool):
    name = "calendar_today"
    description = "List today's Google Calendar events in time order."

    async def run(self) -> dict[str, Any]:
        _require_connected()
        events = await CalendarClient().today()
        return {"events": events, "count": len(events)}


class CreateCalendarEventTool(Tool):
    name = "create_calendar_event"
    description = (
        "Create a Google Calendar event. Start (and optional end) are "
        "ISO-8601 date/times, e.g. 2026-10-03T15:30:00+05:30. "
        "Requires confirmation because it writes to Aarya's calendar."
    )

    async def run(
        self,
        title: str,
        start: str,
        end: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        _require_connected()
        if not title.strip():
            raise ToolError("An event title is required.")
        start_iso = _parse_iso(start)
        end_iso = _parse_iso(end) if end.strip() else ""
        return await CalendarClient().create_event(
            title.strip(), start_iso, end_iso, description.strip()
        )


def _gcsa_calendar():
    """Build a gcsa GoogleCalendar bound to Elsyia's existing OAuth credentials."""
    from gcsa.google_calendar import GoogleCalendar

    return GoogleCalendar(credentials=calendar_oauth().credentials())


_RECURRENCE_RULES = {
    # name -> (gcsa freq, by_week_day)
    "daily": ("DAILY", None),
    "weekly": ("WEEKLY", None),
    "weekdays": ("WEEKLY", ["MO", "TU", "WE", "TH", "FR"]),
    "monthly": ("MONTHLY", None),
    "yearly": ("YEARLY", None),
}


def build_recurrence_rule(
    recurrence: str,
    count: int = 0,
    until: str = "",
) -> str:
    """Build an RFC-5545 RRULE string for a named recurrence via gcsa.

    Raises ToolError on unknown recurrence names or bad count/until values.
    """
    from gcsa.recurrence import FR, MO, SA, SU, TH, TU, WE, Recurrence

    name = (recurrence or "").strip().lower()
    if name not in _RECURRENCE_RULES:
        raise ToolError(
            "Recurrence must be one of: daily, weekly, weekdays, monthly, yearly."
        )
    freq, by_days = _RECURRENCE_RULES[name]
    day_objects = None
    if by_days:
        day_map = {"MO": MO, "TU": TU, "WE": WE, "TH": TH, "FR": FR, "SA": SA, "SU": SU}
        day_objects = [day_map[day] for day in by_days]
    rule_count = None
    if count:
        try:
            rule_count = int(count)
        except (TypeError, ValueError) as exc:
            raise ToolError("count must be a positive integer.") from exc
        if rule_count <= 0:
            raise ToolError("count must be a positive integer.")
    until_dt = None
    if until and until.strip():
        try:
            until_dt = datetime.fromisoformat(until.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ToolError("until must be ISO-8601, e.g. 2026-12-31.") from exc
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
    return Recurrence.rule(
        freq=freq, by_week_day=day_objects, count=rule_count, until=until_dt
    )


class CreateRecurringCalendarEventTool(Tool):
    name = "create_recurring_calendar_event"
    description = (
        "Create a recurring Google Calendar event. Recurrence is one of: "
        "daily, weekly, weekdays (Mon-Fri), monthly, yearly. Optional count "
        "(number of occurrences) or until (ISO-8601 end date). Start (and "
        "optional end) are ISO-8601 date/times; end defaults to start + 1 hour. "
        "Requires confirmation because it writes to Aarya's calendar."
    )

    async def run(
        self,
        title: str,
        start: str,
        end: str = "",
        description: str = "",
        recurrence: str = "weekly",
        count: int = 0,
        until: str = "",
    ) -> dict[str, Any]:
        _require_connected()
        if not title.strip():
            raise ToolError("An event title is required.")
        start_dt = datetime.fromisoformat(_parse_iso(start).replace("Z", "+00:00"))
        end_dt = (
            datetime.fromisoformat(_parse_iso(end).replace("Z", "+00:00"))
            if end.strip()
            else None
        )
        rule = build_recurrence_rule(recurrence, count, until)

        def _call():
            from gcsa.event import Event

            event = Event(
                title.strip(),
                start=start_dt,
                end=end_dt,
                description=description.strip() or None,
                recurrence=[rule],
            )
            created = _gcsa_calendar().add_event(event)
            return {
                "id": getattr(created, "event_id", ""),
                "title": title.strip(),
                "start": start_dt.isoformat(),
                "end": (end_dt or start_dt).isoformat(),
                "recurrence": recurrence.strip().lower(),
                "rrule": rule,
            }

        return await asyncio.to_thread(_call)


class ConnectCalendarTool(Tool):
    name = "connect_calendar"
    description = (
        "Start the one-time Google sign-in that connects Aarya's calendar. "
        "Opens Google's consent page in his browser."
    )

    async def run(self) -> dict[str, str]:
        oauth = calendar_oauth()
        if oauth.is_authorized():
            return {"status": "already_connected"}
        await oauth.authorize_interactive()
        return {"status": "connected"}
