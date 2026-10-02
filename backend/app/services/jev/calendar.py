"""Google Calendar integration for Jev — official Calendar API.

Same user-authorises-on-first-run OAuth pattern as Gmail (see oauth.py).
Capabilities: read today's agenda, create events. Nothing is created in
Aarya's Google account during development.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from typing import Any

from app.core import get_logger
from app.services.jev.oauth import GoogleOAuth
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
            "Google Calendar is not connected yet. Say 'Jev, connect calendar' "
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
