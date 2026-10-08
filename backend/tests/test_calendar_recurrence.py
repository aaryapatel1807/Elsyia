"""Tests for recurring calendar events: intent routing, RRULE building, tool run."""

from datetime import datetime

import pytest

from app.services.elsyia.calendar import (
    CreateRecurringCalendarEventTool,
    build_recurrence_rule,
)
from app.services.tools.base import ToolError
from app.services.tools.intent import route_intent


def _route(text):
    result = route_intent(text)
    assert result is not None, f"no intent routed for {text!r}"
    return result.tool_name, result.arguments, result.confidence


def test_recurring_every_weekday():
    name, args, conf = _route("schedule breakfast every weekday at 8am")
    assert name == "create_recurring_calendar_event"
    assert args["title"] == "breakfast"
    assert args["recurrence"] == "weekdays"
    start = datetime.fromisoformat(args["start"])
    assert (start.hour, start.minute) == (8, 0)
    assert conf >= 0.9


def test_recurring_every_monday():
    name, args, _ = _route("add gym every monday at 6pm")
    assert name == "create_recurring_calendar_event"
    assert args["title"] == "gym"
    assert args["recurrence"] == "weekly"
    start = datetime.fromisoformat(args["start"])
    assert start.weekday() == 0  # Monday
    assert (start.hour, start.minute) == (18, 0)


def test_recurring_daily_and_monthly():
    name, args, _ = _route("schedule standup every day at 9am")
    assert name == "create_recurring_calendar_event"
    assert args["recurrence"] == "daily"

    name, args, _ = _route("schedule rent review every month on the 1st at 10am")
    # "every month" routes recurring; the day-of-month detail falls through
    # to the time parser, which keeps the 10am start.
    assert name == "create_recurring_calendar_event"
    assert args["recurrence"] == "monthly"


def test_recurring_defaults_to_8am_when_no_time():
    name, args, _ = _route("schedule breakfast every weekday")
    assert name == "create_recurring_calendar_event"
    start = datetime.fromisoformat(args["start"])
    assert (start.hour, start.minute) == (8, 0)


def test_plain_events_still_route_to_single_tool():
    name, _, _ = _route("schedule dentist tomorrow at 9am")
    assert name == "create_calendar_event"


def test_every_inside_title_does_not_misroute():
    # "everything" contains "every" but is not a recurrence.
    name, _, _ = _route("schedule everything at 5pm")
    assert name == "create_calendar_event"


def test_build_recurrence_rule_daily():
    rule = build_recurrence_rule("daily")
    assert rule.startswith("RRULE:FREQ=DAILY")


def test_build_recurrence_rule_weekdays():
    rule = build_recurrence_rule("weekdays")
    assert "FREQ=WEEKLY" in rule
    assert "BYDAY=MO,TU,WE,TH,FR" in rule


def test_build_recurrence_rule_with_count_and_until():
    rule = build_recurrence_rule("weekly", count=10)
    assert "COUNT=10" in rule
    rule = build_recurrence_rule("monthly", until="2026-12-31")
    assert "UNTIL=" in rule


def test_build_recurrence_rule_rejects_bad_input():
    with pytest.raises(ToolError):
        build_recurrence_rule("fortnightly")
    with pytest.raises(ToolError):
        build_recurrence_rule("weekly", count=-3)
    with pytest.raises(ToolError):
        build_recurrence_rule("weekly", until="not-a-date")


def test_build_recurrence_rule_zero_count_means_unlimited():
    # count=0 is the tool default: no COUNT clause, the series runs forever.
    assert "COUNT" not in build_recurrence_rule("weekly", count=0)


class _FakeCreatedEvent:
    event_id = "evt_123"


class _FakeGcsaCalendar:
    def __init__(self):
        self.added = []

    def add_event(self, event):
        self.added.append(event)
        return _FakeCreatedEvent()


@pytest.mark.asyncio()
async def test_recurring_tool_run_uses_gcsa(monkeypatch):
    import app.services.elsyia.calendar as cal

    monkeypatch.setattr(cal, "_require_connected", lambda: None)
    fake = _FakeGcsaCalendar()
    monkeypatch.setattr(cal, "_gcsa_calendar", lambda: fake)

    tool = CreateRecurringCalendarEventTool()
    result = await tool.run(
        title="Breakfast",
        start="2026-10-09T08:00:00+05:30",
        recurrence="weekdays",
        count=5,
    )
    assert result["id"] == "evt_123"
    assert result["title"] == "Breakfast"
    assert result["recurrence"] == "weekdays"
    assert "RRULE" in result["rrule"]
    assert "BYDAY=MO,TU,WE,TH,FR" in result["rrule"]
    assert "COUNT=5" in result["rrule"]
    assert len(fake.added) == 1


@pytest.mark.asyncio()
async def test_recurring_tool_rejects_bad_recurrence(monkeypatch):
    import app.services.elsyia.calendar as cal

    monkeypatch.setattr(cal, "_require_connected", lambda: None)

    tool = CreateRecurringCalendarEventTool()
    with pytest.raises(ToolError):
        await tool.run(
            title="X", start="2026-10-09T08:00:00+05:30", recurrence="fortnightly"
        )


def test_recurring_tool_registered_in_registry():
    from app.services.tools import TOOLS_BY_NAME

    assert "create_recurring_calendar_event" in TOOLS_BY_NAME
