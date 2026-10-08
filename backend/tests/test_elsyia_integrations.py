"""Tests for Elsyia's app-integration URL builders and local helpers.

Browser opening is stubbed — these tests assert the exact deep links
Elsyia would open, which is the honest contract of each integration.
"""

import json

import pytest

from app.services.elsyia import contacts as contacts_module
from app.services.tools.base import ToolError
from app.services.tools.integrations import media as media_module
from app.services.tools.integrations.media import (
    linkedin_url,
    press_media_key,
    whatsapp_url,
    youtube_search_url,
    youtube_watch_url,
)


def test_youtube_urls():
    assert youtube_search_url("lofi beats") == (
        "https://www.youtube.com/results?search_query=lofi+beats"
    )
    assert youtube_watch_url("dQw4w9WgXcQ") == (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )


def test_whatsapp_url():
    assert whatsapp_url("919876543210", "hello there") == (
        "https://wa.me/919876543210?text=hello+there"
    )


def test_linkedin_urls():
    assert linkedin_url("feed") == "https://www.linkedin.com/feed/"
    assert linkedin_url("jobs") == "https://www.linkedin.com/jobs/"
    assert linkedin_url("search:data science") == (
        "https://www.linkedin.com/search/results/all/?keywords=data+science"
    )
    assert linkedin_url("profile:aaryapatel") == (
        "https://www.linkedin.com/in/aaryapatel"
    )


async def test_media_keys_rejected_off_windows():
    # This VM is Linux: the tool must fail honestly, not silently.
    with pytest.raises(ToolError):
        await press_media_key("play_pause")


def test_resolve_contact_digits():
    assert contacts_module.resolve_contact("+91 98765 43210") == "919876543210"


def test_resolve_contact_book(tmp_path, monkeypatch):
    book = tmp_path / "contacts.json"
    book.write_text(json.dumps({"mom": "+919999999999"}))
    monkeypatch.setattr(contacts_module, "elsyia_file", lambda name: book)
    assert contacts_module.resolve_contact("mom") == "919999999999"
    assert contacts_module.resolve_contact("MOM") == "919999999999"


def test_resolve_contact_unknown_is_helpful(tmp_path, monkeypatch):
    book = tmp_path / "contacts.json"
    monkeypatch.setattr(contacts_module, "elsyia_file", lambda name: book)
    with pytest.raises(ToolError) as excinfo:
        contacts_module.resolve_contact("nobody")
    assert "contacts.json" in str(excinfo.value)


async def test_play_youtube_without_api_key_opens_search(monkeypatch):
    opened = []

    async def fake_open(url):
        opened.append(url)
        return url

    monkeypatch.setattr(media_module, "open_url", fake_open)

    async def no_api_key(query):
        return None

    monkeypatch.setattr(media_module, "resolve_youtube_video", no_api_key)

    tool = media_module.PlayYouTubeTool()
    result = await tool.run(query="lofi beats")
    assert result["mode"] == "search"
    assert opened == ["https://www.youtube.com/results?search_query=lofi+beats"]
