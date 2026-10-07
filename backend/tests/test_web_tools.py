"""Tests for keyless web search (ddgs) and article extraction (trafilatura)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.tools.base import ToolError
from app.services.tools.intent import route_intent
from app.services.tools.web_tools import FetchUrlTool, SearchWebTool


def test_web_search_intents():
    for text, query in [
        ("search the web for python async", "python async"),
        ("google best laptop 2026", "best laptop 2026"),
        ("look up eiffel tower height", "eiffel tower height"),
    ]:
        result = route_intent(text)
        assert result is not None, text
        assert result.tool_name == "search_web"
        assert result.arguments["query"] == query


class _FakeDDGS:
    def __init__(self, fail_backends=()):
        self._fail = set(fail_backends)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def text(self, query, max_results=5, backend="bing", timeout=15):
        if backend in self._fail:
            raise RuntimeError(f"{backend} blocked")
        return [
            {"title": "Python docs", "href": "https://docs.python.org",
             "body": "Official docs"},
        ]


@pytest.mark.asyncio
async def test_search_web_uses_first_working_backend():
    with patch("ddgs.DDGS",
               return_value=_FakeDDGS(fail_backends={"bing"})):
        result = await SearchWebTool().run(query="python")
    assert result["backend"] == "brave"
    assert result["results"][0]["url"] == "https://docs.python.org"


@pytest.mark.asyncio
async def test_search_web_all_backends_fail():
    with patch("ddgs.DDGS",
               return_value=_FakeDDGS(fail_backends=SearchWebTool._BACKENDS)):
        with pytest.raises(ToolError):
            await SearchWebTool().run(query="python")


@pytest.mark.asyncio
async def test_search_web_rejects_empty_query():
    with pytest.raises(ToolError):
        await SearchWebTool().run(query="  ")


@pytest.mark.asyncio
async def test_fetch_url_extracts_article():
    html = (
        "<html><head><title>T</title></head><body>"
        "<article><p>" + "Word " * 200 + "</p></article>"
        "</body></html>"
    )
    response = MagicMock()
    response.text = html
    response.raise_for_status.return_value = None

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None): return response

    with patch("app.services.tools.web_tools.httpx.AsyncClient",
               return_value=_Client()):
        text = await FetchUrlTool().run(url="https://example.com/article")
    assert "Word" in text
    assert "<article>" not in text  # tags stripped / extracted


@pytest.mark.asyncio
async def test_fetch_url_rejects_bare_host():
    with pytest.raises(ToolError):
        await FetchUrlTool().run(url="example.com")
