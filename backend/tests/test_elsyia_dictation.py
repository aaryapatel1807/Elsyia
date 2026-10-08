"""Tests for Elsyia dictation mode (say it, it types).

The LLM, the microphone, and pynput are all faked — no network, no audio
hardware, no keystrokes leave the test process. The cleanup prompt, the
transcript-cleaning logic, and the typing plumbing are exercised for real.
"""

import sys

import pytest

from app.services.elsyia import dictation
from app.services.elsyia.dictation import (
    DictationUnavailable,
    cleanup_transcript,
    dictation_status,
    load_cleanup_prompt,
    type_text,
)


class _FakeLLM:
    """Yields a canned cleanup result, recording the prompt it got."""

    def __init__(self, reply="Meet at 3pm."):
        self.reply = reply
        self.seen_messages = None

    async def generate(self, messages, **kwargs):
        self.seen_messages = messages
        yield self.reply


@pytest.fixture
def fake_llm(monkeypatch):
    fake = _FakeLLM()

    def _provider(name="ollama"):
        return fake

    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "get_llm_provider", _provider)
    return fake


async def test_cleanup_returns_llm_text_stripped(fake_llm):
    out = await cleanup_transcript("  um hello world  ")
    assert out == "Meet at 3pm."


async def test_cleanup_empty_input_skips_llm(fake_llm):
    assert await cleanup_transcript("") == ""
    assert await cleanup_transcript("   ") == ""
    assert fake_llm.seen_messages is None


async def test_cleanup_prompt_contains_transcript(fake_llm):
    await cleanup_transcript("um so uh meet at 2... no, 3pm")
    prompt = fake_llm.seen_messages[0]["content"]
    assert "um so uh meet at 2... no, 3pm" in prompt
    assert "{transcript}" not in prompt


async def test_cleanup_strips_quoted_wrapping(fake_llm):
    fake_llm.reply = '"Meet at 3pm."'
    assert await cleanup_transcript("meet at 3pm") == "Meet at 3pm."


def test_cleanup_prompt_file_has_rules():
    prompt = load_cleanup_prompt()
    assert "filler words" in prompt.lower()
    assert "self-corrections" in prompt.lower()
    assert "{transcript}" in prompt
    # The prompt must forbid the model from answering instead of cleaning.
    assert "do not answer questions" in prompt.lower()


def test_type_text_without_pynput_raises_clean_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynput", None)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", None)
    with pytest.raises(DictationUnavailable, match="pynput"):
        type_text("hello")


def test_type_text_uses_pynput_controller(monkeypatch):
    typed: list = []

    class _FakeController:
        def type(self, s):
            typed.append(s)

    import types

    fake_kb = types.ModuleType("pynput.keyboard")
    fake_kb.Controller = _FakeController
    fake_pkg = types.ModuleType("pynput")
    fake_pkg.keyboard = fake_kb
    monkeypatch.setitem(sys.modules, "pynput", fake_pkg)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_kb)

    assert type_text("hello world") == 11
    assert "".join(typed) == "hello world"


def test_type_text_empty_is_noop():
    assert type_text("") == 0


def test_type_text_chunks_long_input(monkeypatch):
    typed: list = []

    class _FakeController:
        def type(self, s):
            typed.append(s)

    import types

    fake_kb = types.ModuleType("pynput.keyboard")
    fake_kb.Controller = _FakeController
    fake_pkg = types.ModuleType("pynput")
    fake_pkg.keyboard = fake_kb
    monkeypatch.setitem(sys.modules, "pynput", fake_pkg)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_kb)

    long_text = "x" * 1000
    assert type_text(long_text) == 1000
    assert "".join(typed) == long_text
    assert len(typed) > 1  # chunked, not one giant paste


def test_dictation_status_shape():
    status = dictation_status()
    assert "hotkey" in status and status["hotkey"]
    assert "confirm" in status
    assert "typing_available" in status
    assert status["on_device"] is True
