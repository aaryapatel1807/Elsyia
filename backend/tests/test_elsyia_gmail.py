"""Tests for the Gmail client with a mocked Google API.

Never touches a live mailbox: googleapiclient.discovery.build is stubbed.
"""

import base64

import pytest

import app.services.elsyia.gmail as gmail_module
from app.services.elsyia.gmail import GmailClient, _extract_plain_text
from app.services.tools.base import ToolError


class _FakeMessages:
    def __init__(self, store):
        self._store = store
        self._op = None

    # list()
    def list(self, userId=None, q=None, maxResults=None):
        self._op = ("list", q)
        return self

    # get()
    def get(self, userId=None, id=None, format=None, metadataHeaders=None):
        self._op = ("get", id, format)
        return self

    # send()
    def send(self, userId=None, body=None):
        self._op = ("send", body)
        return self

    def execute(self):
        op = self._op[0]
        if op == "list":
            return {"messages": [{"id": m["id"]} for m in self._store]}
        if op == "get":
            msg_id = self._op[1]
            return next(m for m in self._store if m["id"] == msg_id)
        if op == "send":
            return {"id": "sent-123"}
        raise AssertionError(op)


class _FakeService:
    def __init__(self, store):
        self._messages = _FakeMessages(store)

    def users(self):
        return self

    def messages(self):
        return self._messages


def _message(msg_id, frm, subject, snippet, body_text):
    body = base64.urlsafe_b64encode(body_text.encode()).decode()
    return {
        "id": msg_id,
        "snippet": snippet,
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": frm},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Fri, 02 Oct 2026 10:00:00 +0530"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": body},
                }
            ],
        },
    }


@pytest.fixture
def fake_build(monkeypatch):
    store = [
        _message("m1", "boss@corp.com", "Report due", "snippet one", "Hello world body"),
        _message("m2", "news@list.com", "Weekly digest", "snippet two", "Digest body"),
    ]
    monkeypatch.setattr(
        gmail_module, "_service", lambda: _FakeService(store)
    )
    monkeypatch.setattr(gmail_module, "_require_connected", lambda: None)
    return store


async def test_list_unread(fake_build):
    messages = await GmailClient().list_unread()
    assert len(messages) == 2
    assert messages[0]["from"] == "boss@corp.com"
    assert messages[0]["subject"] == "Report due"


async def test_search(fake_build):
    messages = await GmailClient().search("invoice")
    assert len(messages) == 2  # fake ignores the query; shape is what matters
    assert all("id" in m and "snippet" in m for m in messages)


async def test_read_extracts_plain_text(fake_build):
    detail = await GmailClient().read("m1")
    assert detail["from"] == "boss@corp.com"
    assert "Hello world body" in detail["body"]


async def test_send_shape(fake_build):
    result = await GmailClient().send("a@b.com", "hi", "hello")
    assert result["id"] == "sent-123"
    assert result["to"] == "a@b.com"


def test_extract_plain_text_nested():
    inner = base64.urlsafe_b64encode(b"nested body").decode()
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [{"mimeType": "text/plain", "body": {"data": inner}}],
    }
    assert _extract_plain_text(payload) == "nested body"


async def test_tools_reject_bad_input(fake_build):
    with pytest.raises(ToolError):
        await gmail_module.SendGmailTool().run(to="not-an-email", subject="s", body="b")
    with pytest.raises(ToolError):
        await gmail_module.SearchGmailTool().run(query="   ")
