"""Generic Google OAuth2 desktop-app flow for Elsyia integrations.

How it works for Aarya (documented in the README):
1. He creates his own OAuth client once in Google Cloud Console
   (Desktop app type) — nothing is created for him.
2. He sets ELSYIA_GOOGLE_CLIENT_JSON to the downloaded client JSON
   (or ELSYIA_GOOGLE_CLIENT_ID / ELSYIA_GOOGLE_CLIENT_SECRET).
3. On first use he says "Elsyia, connect Gmail" — Elsyia opens Google's
   consent page in his browser; Google redirects back to a local
   callback and the token is stored at ~/.elsyia/ for future runs.

No Google credentials ever live in the repo. Tokens are per-service so
Gmail and Calendar authorise independently.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Sequence

from app.core import get_logger, get_settings
from app.services.elsyia.paths import elsyia_file
from app.services.tools.base import ToolError

logger = get_logger(__name__)


def _load_client_config() -> dict:
    settings = get_settings()
    json_path = getattr(settings, "ELSYIA_GOOGLE_CLIENT_JSON", "") or ""
    if json_path:
        try:
            return json.loads(_read(json_path))
        except OSError as exc:
            raise ToolError(
                f"Could not read ELSYIA_GOOGLE_CLIENT_JSON at {json_path}: {exc}"
            ) from exc
    client_id = getattr(settings, "ELSYIA_GOOGLE_CLIENT_ID", "") or ""
    client_secret = getattr(settings, "ELSYIA_GOOGLE_CLIENT_SECRET", "") or ""
    if client_id and client_secret:
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    raise ToolError(
        "Google OAuth is not configured. Set ELSYIA_GOOGLE_CLIENT_JSON to your "
        "OAuth client JSON (Desktop app), or ELSYIA_GOOGLE_CLIENT_ID and "
        "ELSYIA_GOOGLE_CLIENT_SECRET. See the README for the one-time setup."
    )


def _read(path: str) -> str:
    from pathlib import Path

    return Path(path).expanduser().read_text(encoding="utf-8")


@dataclass
class GoogleOAuth:
    """OAuth2 state for one Google service (gmail, calendar)."""

    service: str
    scopes: Sequence[str]

    @property
    def token_path(self):
        return elsyia_file(f"google_token_{self.service}.json")

    def _load_credentials(self):
        from google.oauth2.credentials import Credentials

        if not self.token_path.exists():
            return None
        return Credentials.from_authorized_user_file(
            str(self.token_path), list(self.scopes)
        )

    def is_authorized(self) -> bool:
        creds = self._load_credentials()
        if creds is None:
            return False
        if creds.expired and not creds.refresh_token:
            return False
        return True

    def credentials(self):
        """Return valid credentials, refreshing silently when possible."""
        from google.auth.transport.requests import Request

        creds = self._load_credentials()
        if creds is None:
            raise ToolError(
                f"{self.service.title()} is not connected yet. "
                f"Ask me to 'connect {self.service}' first."
            )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        if not creds.valid:
            raise ToolError(
                f"The {self.service} authorisation expired. "
                f"Ask me to 'connect {self.service}' again."
            )
        return creds

    def _run_interactive_flow(self) -> None:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(
            _load_client_config(), list(self.scopes)
        )
        # Opens the consent page in Aarya's browser and listens on a local
        # port for Google's redirect — the standard desktop-app pattern.
        creds = flow.run_local_server(port=0, open_browser=True)
        self.token_path.write_text(creds.to_json(), encoding="utf-8")
        logger.info("Google OAuth completed for service=%s", self.service)

    async def authorize_interactive(self) -> None:
        """Run the browser-based consent flow without blocking the server."""
        await asyncio.to_thread(self._run_interactive_flow)
