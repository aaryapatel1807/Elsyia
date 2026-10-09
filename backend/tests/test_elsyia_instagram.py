"""Tests for Elsyia's Instagram Reels tools.

The instagram-cli is stubbed — these tests assert the connector logic
(own reels -> following feed -> browser fallback) and the exact URLs
Elsyia would open, without touching the network.
"""

import pytest

from app.services.tools.base import ToolError
from app.services.tools.integrations import social as social_module
from app.services.tools.integrations.social import (
    DescribeInstagramReelTool,
    ShowInstagramReelsTool,
    _extract_summary,
)
from app.services.tools.intent import route_intent


def _posts_payload(posts):
    return {"posts": posts}


def _reel(username, caption, url):
    return {
        "username": username,
        "post_caption": caption,
        "url": url,
        "post_id": "1",
        "media_type": "video",
    }


async def test_show_reels_own_reels_connector(monkeypatch):
    opened = []

    async def fake_open(url):
        opened.append(url)
        return url

    async def router(*args):
        if args[0] == "accounts":
            return {"accounts": [{"user_fbid": "123"}]}
        return _posts_payload(
            [_reel("aarya.x_07", "my new reel", "https://www.instagram.com/reel/abc/")]
        )

    monkeypatch.setattr(social_module, "_run_cli", router)
    monkeypatch.setattr(social_module, "open_url", fake_open)
    social_module._account_cache = None

    res = await ShowInstagramReelsTool().run(query="")
    assert res["mode"] == "connector"
    assert res["source"] == "your reels"
    assert opened == ["https://www.instagram.com/reel/abc/"]
    social_module._account_cache = None


async def test_show_reels_falls_back_to_feed(monkeypatch):
    opened = []

    async def fake_open(url):
        opened.append(url)
        return url

    async def router(*args):
        if args[0] == "accounts":
            return {"accounts": [{"user_fbid": "123"}]}
        if args[0] == "posts":
            return _posts_payload([])  # no own reels
        if args[0] == "feed":
            return _posts_payload(
                [_reel("athar.codes", "train ai", "", )]
            )
        if args[0] == "post":
            return _posts_payload(
                [_reel("athar.codes", "train ai", "https://www.instagram.com/reel/xyz/")]
            )
        raise AssertionError(args)

    monkeypatch.setattr(social_module, "_run_cli", router)
    monkeypatch.setattr(social_module, "open_url", fake_open)
    social_module._account_cache = None

    res = await ShowInstagramReelsTool().run(query="")
    assert res["mode"] == "connector"
    assert res["source"] == "your following feed"
    assert opened == ["https://www.instagram.com/reel/xyz/"]
    social_module._account_cache = None


async def test_show_reels_query_filters(monkeypatch):
    async def router(*args):
        if args[0] == "accounts":
            return {"accounts": [{"user_fbid": "123"}]}
        return _posts_payload(
            [
                _reel("u1", "cricket highlights", "https://www.instagram.com/reel/c1/"),
                _reel("u2", "cooking pasta", "https://www.instagram.com/reel/c2/"),
            ]
        )

    async def fake_open(url):
        return url

    monkeypatch.setattr(social_module, "_run_cli", router)
    monkeypatch.setattr(social_module, "open_url", fake_open)
    social_module._account_cache = None

    res = await ShowInstagramReelsTool().run(query="cricket")
    assert res["mode"] == "connector"
    assert len(res["reels"]) == 1
    assert res["reels"][0]["caption"] == "cricket highlights"
    social_module._account_cache = None


async def test_show_reels_browser_fallback_when_no_cli(monkeypatch):
    opened = []

    async def fake_open(url):
        opened.append(url)
        return url

    async def no_cli(*args):
        raise ToolError("instagram-cli is not installed on this machine.")

    monkeypatch.setattr(social_module, "_run_cli", no_cli)
    monkeypatch.setattr(social_module, "open_url", fake_open)
    social_module._account_cache = None

    res = await ShowInstagramReelsTool().run(query="")
    assert res["mode"] == "browser"
    assert opened == ["https://www.instagram.com/reels/"]
    social_module._account_cache = None


async def test_describe_reel_returns_summary(monkeypatch):
    async def router(*args):
        if args[0] == "accounts":
            return {"accounts": [{"user_fbid": "123"}]}
        if args[0] == "post":
            return _posts_payload(
                [_reel("athar.codes", "train ai", "https://www.instagram.com/reel/xyz/")]
            )
        if args[0] == "media-understanding":
            return {"media": [{"narrative_summary": "A man explains GPUs."}]}
        raise AssertionError(args)

    monkeypatch.setattr(social_module, "_run_cli", router)
    social_module._account_cache = None

    res = await DescribeInstagramReelTool().run(
        url="https://www.instagram.com/reel/xyz/"
    )
    assert res["username"] == "athar.codes"
    assert res["summary"] == "A man explains GPUs."
    social_module._account_cache = None


async def test_describe_reel_rejects_bad_url():
    with pytest.raises(ToolError):
        await DescribeInstagramReelTool().run(url="not a url")


def test_extract_summary_shapes():
    assert _extract_summary({"media": [{"narrative_summary": "hello"}]}) == "hello"
    assert _extract_summary({"summary": "s"}) == "s"
    assert _extract_summary({}) == ""
    assert _extract_summary([]) == ""


def test_intent_show_reels():
    routed = route_intent("show me reels")
    assert routed is not None and routed.tool_name == "show_instagram_reels"
    assert routed.arguments["query"] == ""

    routed = route_intent("show reels about cricket")
    assert routed is not None and routed.tool_name == "show_instagram_reels"
    assert routed.arguments["query"] == "cricket"

    routed = route_intent("open instagram reels")
    assert routed is not None and routed.tool_name == "show_instagram_reels"
