"""
Web Tools

Ported from the FRIDAY reference project's friday/tools/web.py — the RSS
aggregation and URL-fetch logic is kept (it's generic and useful),
reworked from MCP @mcp.tool() functions into plain Tool subclasses.

Dropped during the port:
  - open_world_monitor / open_finance_world_monitor: these called
    webbrowser.open() on a specific hardcoded third-party site
    (worldmonitor.app). That's a product decision specific to the FRIDAY
    demo, not a generic capability, so it wasn't carried over. Add it
    back deliberately if Elysia actually wants a "launch a URL" tool —
    that's a different, more general tool than opening one fixed site.
  - The Tony Stark "sir" phrasing in error strings was replaced with
    plain text per docs/PERSONALITY.md ("assistant, not a servant").
"""

import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.core import get_settings
from app.services.tools.base import Tool, ToolError

_WORLD_NEWS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
]

_FINANCE_NEWS_FEEDS = [
    "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "https://feeds.bloomberg.com/markets/news.rss",
    "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
]


async def _fetch_and_parse_feed(client: httpx.AsyncClient, url: str) -> list[dict[str, str]]:
    """Fetch a single RSS feed and parse its top items. Fails soft (empty list)."""
    try:
        response = await client.get(
            url,
            headers={"User-Agent": "Elysia/0.1"},
            timeout=get_settings().REALTIME_DATA_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        if response.status_code != 200:
            return []

        root = ET.fromstring(response.content)
        source_name = url.split(".")[1].upper()

        items: list[dict[str, str]] = []
        for item in root.findall(".//item")[:5]:
            title = item.findtext("title") or ""
            description = item.findtext("description") or ""
            link = item.findtext("link") or ""

            description = re.sub("<[^<]+?>", "", description).strip()

            items.append(
                {
                    "source": source_name,
                    "title": title,
                    "summary": (description[:200] + "...") if description else "",
                    "link": link,
                }
            )
        return items
    except Exception:
        return []


async def _aggregate_feeds(feeds: list[str]) -> list[dict[str, str]]:
    import asyncio

    if not get_settings().REALTIME_DATA_ENABLED:
        raise ToolError("Real-time data is disabled. Set REALTIME_DATA_ENABLED=true to enable the allowlisted feeds.")
    async with httpx.AsyncClient(follow_redirects=False, timeout=get_settings().REALTIME_DATA_TIMEOUT_SECONDS) as client:
        results = await asyncio.gather(*(_fetch_and_parse_feed(client, url) for url in feeds))
    return [item for sublist in results for item in sublist][: get_settings().REALTIME_DATA_MAX_ITEMS]


class GetWorldNewsTool(Tool):
    """Fetches current global headlines from several major news outlets."""

    name = "get_world_news"
    description = (
        "Fetch the latest global headlines from major news outlets. "
        "Use for 'what's happening in the world' or recent-events questions."
    )

    async def run(self, **kwargs: Any) -> list[dict[str, str]]:
        articles = await _aggregate_feeds(_WORLD_NEWS_FEEDS)
        if not articles:
            raise ToolError("Unable to reach any news feeds right now.")
        return articles[:12]


class GetWorldFinanceNewsTool(Tool):
    """Fetches current finance/market headlines from major financial outlets."""

    name = "get_world_finance_news"
    description = (
        "Fetch the latest finance and market headlines. "
        "Use for market updates or economic-news questions."
    )

    async def run(self, **kwargs: Any) -> list[dict[str, str]]:
        articles = await _aggregate_feeds(_FINANCE_NEWS_FEEDS)
        if not articles:
            raise ToolError("Unable to reach any finance feeds right now.")
        return articles[:12]


class FetchUrlTool(Tool):
    """Fetches a URL and extracts its readable article text."""

    name = "fetch_url"
    description = (
        "Fetch a web page and extract its main readable text "
        "(article extraction via trafilatura, raw-text fallback)."
    )

    async def run(self, url: str, **kwargs: Any) -> str:
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ToolError("fetch_url needs a full http(s) URL.")
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            response = await client.get(
                url, headers={"User-Agent": "elsyia-assistant/1.0"}
            )
            response.raise_for_status()
            html = response.text
        try:
            from trafilatura import extract

            text = extract(
                html, include_comments=False, include_tables=True,
                no_fallback=False,
            )
            if text and len(text.strip()) > 200:
                return text.strip()[:8000]
        except ImportError:
            pass
        except Exception:  # noqa: BLE001 — fall back to raw text
            pass
        import re as _re

        text = _re.sub(r"<script.*?</script>", " ", html, flags=_re.S | _re.I)
        text = _re.sub(r"<style.*?</style>", " ", text, flags=_re.S | _re.I)
        text = _re.sub(r"<[^>]+>", " ", text)
        return " ".join(text.split())[:4000]


class SearchWebTool(Tool):
    """Keyless web search via ddgs (metasearch, no API key needed)."""

    name = "search_web"
    description = (
        "Search the web for a query and return titles, URLs and snippets. "
        "Keyless metasearch (ddgs) — no API key required."
    )

    # Backends tried in order; different networks block different engines.
    _BACKENDS = ("bing", "brave", "duckduckgo", "mojeek", "google")

    async def run(self, query: str, max_results: int = 5, **kwargs: Any) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise ToolError("search_web needs a query.")
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise ToolError(
                "Web search needs the 'ddgs' package (pip install ddgs)."
            ) from exc
        max_results = max(1, min(int(max_results or 5), 10))
        last_error: str | None = None
        for backend in self._BACKENDS:
            try:
                with DDGS() as ddgs:
                    raw = list(ddgs.text(
                        query, max_results=max_results,
                        backend=backend, timeout=15,
                    ))
                results = [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                    for r in raw
                    if r.get("href")
                ]
                if results:
                    return {"query": query, "backend": backend, "results": results}
                last_error = f"{backend}: no results"
            except Exception as exc:  # noqa: BLE001 — try next backend
                last_error = f"{backend}: {exc}"
                continue
        raise ToolError(f"Web search failed on all backends ({last_error}).")
