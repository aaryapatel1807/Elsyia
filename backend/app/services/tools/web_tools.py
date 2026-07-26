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
        response = await client.get(url, headers={"User-Agent": "Elysia/0.1"}, timeout=5.0)
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

    async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
        results = await asyncio.gather(*(_fetch_and_parse_feed(client, url) for url in feeds))
    return [item for sublist in results for item in sublist]


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
    """Fetches the raw text content of a URL."""

    name = "fetch_url"
    description = "Fetch the raw text content of a given URL."

    async def run(self, url: str, **kwargs: Any) -> str:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text[:4000]


class SearchWebTool(Tool):
    """Searches the web for a query. Not yet implemented — stub, same as in FRIDAY."""

    name = "search_web"
    description = "Search the web for a given query and return a summary of results."

    async def run(self, query: str, **kwargs: Any) -> str:
        # TODO: wire to a real search provider. Left as a stub deliberately —
        # it was a stub in the FRIDAY source too, not a regression from the port.
        raise ToolError(f"search_web is not yet implemented (query was: {query!r})")
