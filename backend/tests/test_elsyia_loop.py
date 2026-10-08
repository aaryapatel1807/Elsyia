"""Tests for the Elsyia loop: intent fast-path, confirmation, LLM fallback.

The LLM and Gmail API are faked/mocked — no network, no live mailbox.
"""

import pytest

from app.services.elsyia.loop import ElsyiaLoop


class _FakeLLM:
    def __init__(self, reply="At your service."):
        self.reply = reply

    async def generate(self, messages, system_prompt=None, **kwargs):
        yield self.reply


@pytest.fixture
def loop(monkeypatch):
    import app.services.elsyia.loop as loop_module

    fake = _FakeLLM()
    monkeypatch.setattr(loop_module.ElsyiaLoop, "_llm_provider", lambda self: fake)
    return ElsyiaLoop(), fake


async def test_tool_fast_path_time(loop):
    elsyia, _ = loop
    result = await elsyia.handle_text("what time is it")
    assert result.intent == "get_current_time"
    assert result.actions and result.actions[0]["status"] == "ok"
    assert result.reply.startswith("It's ")
    assert result.timings_ms["total_ms"] < 5000


async def test_conversational_path_uses_elsyia_persona(loop):
    elsyia, fake = loop
    result = await elsyia.handle_text("tell me a joke about butlers")
    assert result.intent == "none"
    assert result.reply == "At your service."
    assert not result.actions


async def test_empty_text(loop):
    elsyia, _ = loop
    result = await elsyia.handle_text("   ")
    assert "didn't catch" in result.reply


async def test_send_gmail_requires_confirmation(loop):
    elsyia, _ = loop
    result = await elsyia.handle_text(
        "send email to a@b.com subject hi saying hello there"
    )
    assert result.intent == "send_gmail"
    action = result.actions[0]
    assert action["status"] == "confirmation_required"
    assert action["confirmation_required"] is True
    assert "Confirm" in result.reply or "confirm" in result.reply


async def test_send_gmail_confirmed_with_mock(loop, monkeypatch):
    import app.services.elsyia.gmail as gmail_module

    sent = {}

    class FakeGmailClient:
        async def send(self, to, subject, body):
            sent.update(to=to, subject=subject, body=body)
            return {"id": "mock-id", "to": to, "subject": subject}

    monkeypatch.setattr(gmail_module, "GmailClient", FakeGmailClient)
    # Pretend OAuth is done so we reach the client.
    monkeypatch.setattr(gmail_module, "_require_connected", lambda: None)

    elsyia, _ = loop
    result = await elsyia.handle_text(
        "send email to a@b.com subject hi saying hello there",
        confirmed={"send_gmail"},
    )
    action = result.actions[0]
    assert action["status"] == "ok"
    assert sent["to"] == "a@b.com"
    assert "a@b.com" in result.reply


async def test_gmail_not_connected_message(loop):
    elsyia, _ = loop
    result = await elsyia.handle_text("check my email")
    assert result.actions[0]["status"] == "error"
    assert "not connected" in result.reply


async def test_whatsapp_unknown_contact_is_honest(loop):
    elsyia, _ = loop
    result = await elsyia.handle_text("message zzzunknown on whatsapp saying hi")
    assert result.actions[0]["status"] == "error"
    assert "don't have" in result.reply or "WhatsApp number" in result.reply
