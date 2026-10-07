"""Tests for natural-language time parsing (voice-friendly datetimes)."""

from datetime import datetime, timedelta

from app.services.tools.timeparse import (
    parse_datetime,
    parse_duration,
    words_to_number,
)


def test_words_to_number():
    assert words_to_number("five") == 5
    assert words_to_number("twenty two") == 22
    assert words_to_number("a") == 1
    assert words_to_number("7") == 7
    assert words_to_number("banana") is None


def test_parse_duration_units():
    assert parse_duration("5 minutes") == timedelta(minutes=5)
    assert parse_duration("two hours") == timedelta(hours=2)
    assert parse_duration("30 secs") == timedelta(seconds=30)
    assert parse_duration("1 day") == timedelta(days=1)
    assert parse_duration("half an hour") == timedelta(minutes=30)
    assert parse_duration("tomorrow") is None


def _now():
    return datetime(2026, 10, 8, 10, 0, 0).astimezone()  # Thursday 10:00


def test_parse_in_duration():
    result = parse_datetime("in 5 minutes", now=_now())
    assert result == _now() + timedelta(minutes=5)
    result = parse_datetime("in two hours", now=_now())
    assert result == _now() + timedelta(hours=2)


def test_parse_tomorrow_at():
    result = parse_datetime("tomorrow at 5pm", now=_now())
    assert result is not None
    assert (result.day, result.hour, result.minute) == (9, 17, 0)


def test_parse_today_at():
    result = parse_datetime("remind me today at 7:30", now=_now())
    assert result is not None
    # 7:30am already passed at 10:00 with no am/pm -> 19:30 today.
    assert (result.day, result.hour, result.minute) == (8, 19, 30)


def test_parse_next_monday():
    # 2026-10-08 is a Thursday; next Monday is 2026-10-12.
    result = parse_datetime("next monday at 9am", now=_now())
    assert result is not None
    assert (result.day, result.hour) == (12, 9)


def test_parse_bare_weekday_future():
    # Bare "friday" from Thursday -> tomorrow (Oct 9).
    result = parse_datetime("friday at 6pm", now=_now())
    assert result is not None
    assert (result.day, result.hour) == (9, 18)


def test_parse_at_time_next_occurrence():
    # 10:00 now; "at 7pm" is later today.
    result = parse_datetime("at 7pm", now=_now())
    assert result is not None
    assert (result.day, result.hour) == (8, 19)
    # "at 9am" already passed -> tomorrow.
    result = parse_datetime("at 9am", now=_now())
    assert result is not None
    assert (result.day, result.hour) == (9, 9)


def test_parse_garbage_returns_none():
    assert parse_datetime("blorple the zzz", now=_now()) is None
