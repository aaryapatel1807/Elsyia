"""Jev app integrations — real, free, ToS-safe.

Each integration here genuinely works end-to-end from a voice command.
The approach is honest about platform limits:

- YouTube: official Data API (free quota) to resolve the exact video when
  a key is configured; otherwise a search deep link. Playback control via
  system media keys.
- WhatsApp: wa.me deep links open the right chat with text prefilled,
  ready to send. There is no free official API for personal WhatsApp
  messaging or reading chats, so no scrapers or unofficial automation —
  the prefilled deep link IS the real version of this.
- LinkedIn: deep links for feed, jobs, search and profiles. Posting via
  API needs a LinkedIn partnership and is not available — documented,
  not faked.
- Spotify: open.spotify.com deep links + system media keys. The full Web
  API needs per-user OAuth and Spotify Premium for playback control;
  documented as a future step, not faked.
"""

from app.services.tools.integrations.media import (
    MediaControlTool,
    MessageWhatsAppTool,
    OpenLinkedInTool,
    OpenSpotifyTool,
    PlayYouTubeTool,
)
from app.services.tools.integrations.productivity import (
    ReadNotesTool,
    SetTimerTool,
    TakeNoteTool,
)

__all__ = [
    "MediaControlTool",
    "MessageWhatsAppTool",
    "OpenLinkedInTool",
    "OpenSpotifyTool",
    "PlayYouTubeTool",
    "ReadNotesTool",
    "SetTimerTool",
    "TakeNoteTool",
]
