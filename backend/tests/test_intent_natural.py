"""Tests for natural-language intent routing (timeparse wiring + fuzzy fallback)."""

from datetime import datetime

from app.services.tools.intent import route_intent


def _route(text):
    result = route_intent(text)
    assert result is not None, f"no intent routed for {text!r}"
    return result.tool_name, result.arguments, result.confidence


def test_timer_natural_durations():
    name, args, _ = _route("set a timer for 10 minutes")
    assert (name, args["minutes"]) == ("set_timer", 10)
    name, args, _ = _route("set a timer for two hours")
    assert (name, args["minutes"]) == ("set_timer", 120)
    name, args, _ = _route("set a timer for 30 seconds called tea")
    assert (name, args["minutes"], args["label"]) == ("set_timer", 1, "tea")
    name, args, _ = _route("timer for five minutes")
    assert (name, args["minutes"]) == ("set_timer", 5)


def test_timer_nonsense_falls_through():
    assert route_intent("set a timer for the meeting") is None


def test_reminder_natural_in():
    name, args, _ = _route("remind me to stretch in five minutes")
    assert name == "create_reminder"
    assert args["title"] == "stretch"
    due = datetime.fromisoformat(args["due_at"])
    assert 4 <= (due - datetime.now(due.tzinfo)).total_seconds() / 60 <= 6

    # Greedy title: the LAST "in" wins.
    name, args, _ = _route("remind me to check in on mom in 2 hours")
    assert name == "create_reminder"
    assert args["title"] == "check in on mom"


def test_reminder_natural_at():
    name, args, _ = _route("remind me to call mom tomorrow at 5pm")
    assert name == "create_reminder"
    assert args["title"] == "call mom"
    due = datetime.fromisoformat(args["due_at"])
    assert (due.hour, due.minute) == (17, 0)


def test_calendar_natural():
    name, args, conf = _route("schedule dentist tomorrow at 9am")
    assert name == "create_calendar_event"
    assert args["title"] == "dentist"
    start = datetime.fromisoformat(args["start"])
    assert (start.hour, start.minute) == (9, 0)
    assert conf >= 0.9


def test_fuzzy_fallback_near_miss():
    name, args, conf = _route("could you check my inbox please")
    assert name == "check_gmail"
    assert conf < 0.9  # fuzzy, not regex
    name, _, _ = _route("hey elsyia what is on my clipboard")
    assert name == "read_clipboard"


def test_fuzzy_fallback_ignores_chat():
    assert route_intent("tell me about the roman empire") is None
    assert route_intent("what do you think about pineapple pizza") is None


def test_old_iso_paths_still_work():
    name, args, _ = _route("remind me to stretch in 5 minutes")
    assert name == "create_reminder" and args["title"] == "stretch"
