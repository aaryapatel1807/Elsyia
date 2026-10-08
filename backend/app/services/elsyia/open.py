"""Cross-platform URL opening for Elsyia integrations.

Deep links are the honest, ToS-safe way to drive apps that offer no free
official automation API (YouTube, WhatsApp, LinkedIn, Spotify): the voice
command resolves to the exact URL and the system opens it in the default
browser or app, ready to use.
"""

from __future__ import annotations

import asyncio
import webbrowser

from app.core import get_logger

logger = get_logger(__name__)


async def open_url(url: str) -> str:
    """Open a URL in the default browser/app. Returns the opened URL."""
    logger.info("Elsyia opening URL: %s", url)
    await asyncio.to_thread(webbrowser.open, url, new=2)
    return url
