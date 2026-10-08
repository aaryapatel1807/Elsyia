"""Tests for Elsyia's deterministic voice-command intent routing."""

from app.services.tools.intent import route_intent


def _route(text):
    result = route_intent(text)
    assert result is not None, f"no intent routed for {text!r}"
    return result.tool_name, result.arguments


def test_youtube_play():
    assert _route("play despacito on youtube") == (
        "play_youtube", {"query": "despacito"},
    )


def test_media_controls():
    assert _route("pause") == ("media_control", {"action": "pause"})
    assert _route("next song") == ("media_control", {"action": "next"})
    assert _route("previous") == ("media_control", {"action": "previous"})


def test_whatsapp():
    name, args = _route("message mom on whatsapp saying I will be late")
    assert name == "message_whatsapp"
    assert args == {"to": "mom", "text": "I will be late"}
    name, args = _route("whatsapp +919876543210 hello there")
    assert name == "message_whatsapp"
    assert args["to"] == "+919876543210"


def test_linkedin():
    assert _route("open linkedin") == ("open_linkedin", {"target": "feed"})
    assert _route("open linkedin jobs") == ("open_linkedin", {"target": "jobs"})
    name, args = _route("search linkedin for data science internships")
    assert name == "open_linkedin"
    assert args["target"].startswith("search:")


def test_spotify():
    name, args = _route("play lo-fi beats on spotify")
    assert name == "open_spotify"
    assert args == {"query": "lo-fi beats"}
    assert _route("open spotify") == ("open_spotify", {})


def test_gmail_intents():
    assert _route("check my email")[0] == "check_gmail"
    name, args = _route("search my emails for invoice")
    assert (name, args) == ("search_gmail", {"query": "invoice"})
    assert _route("connect gmail")[0] == "connect_gmail"
    name, args = _route(
        "send email to a@b.com subject hello saying this is a test"
    )
    assert name == "send_gmail"
    assert args["to"] == "a@b.com"


def test_calendar_intents():
    assert _route("what's on my calendar")[0] == "calendar_today"
    name, args = _route("schedule dentist at 2026-10-04T10:00:00+05:30")
    assert name == "create_calendar_event"
    assert args["title"] == "dentist"
    assert _route("connect calendar")[0] == "connect_calendar"


def test_timer_and_notes():
    name, args = _route("set timer for 5 minutes called tea")
    assert name == "set_timer"
    assert args == {"minutes": 5, "label": "tea"}
    name, args = _route("take a note buy milk tomorrow")
    assert (name, args) == ("take_note", {"text": "buy milk tomorrow"})
    assert _route("read my notes")[0] == "read_notes"


def test_existing_intents_unaffected():
    assert _route("what time is it")[0] == "get_current_time"
    assert _route("open calculator")[0] == "launch_application"
    assert route_intent("hello how are you") is None
