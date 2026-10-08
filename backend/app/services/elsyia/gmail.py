"""Gmail integration for Elsyia — official Gmail API, user-authorised OAuth.

Capabilities (real, via the official API):
- list unread inbox messages (sender, subject, snippet, date)
- search mail with Gmail search operators
- read a message body as plain text
- send email on voice command

Hard boundary: Elsyia never touches Aarya's live mailbox during
development — the test-suite mocks the API client. OAuth setup is a
one-time documented step he performs himself.
"""

from __future__ import annotations

import asyncio
import base64
from email.message import EmailMessage
from typing import Any

from app.core import get_logger
from app.services.elsyia.oauth import GoogleOAuth
from app.services.tools.base import Tool, ToolError

logger = get_logger(__name__)

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def gmail_oauth() -> GoogleOAuth:
    return GoogleOAuth(service="gmail", scopes=GMAIL_SCOPES)


def _service():
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=gmail_oauth().credentials())


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    return {
        h["name"].lower(): h["value"]
        for h in payload.get("headers", [])
        if "name" in h and "value" in h
    }


def _metadata_to_summary(message: dict[str, Any]) -> dict[str, str]:
    headers = _headers(message.get("payload", {}))
    return {
        "id": message.get("id", ""),
        "from": headers.get("from", "(unknown sender)"),
        "subject": headers.get("subject", "(no subject)"),
        "date": headers.get("date", ""),
        "snippet": message.get("snippet", ""),
    }


def _extract_plain_text(payload: dict[str, Any]) -> str:
    """Walk a Gmail payload and return the text/plain body."""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})
    if mime.startswith("text/plain") and body.get("data"):
        return base64.urlsafe_b64decode(body["data"]).decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text.strip():
            return text
    if mime.startswith("text/html") and body.get("data"):
        # Last resort: strip tags from the HTML part.
        import re

        html = base64.urlsafe_b64decode(body["data"]).decode("utf-8", "replace")
        return re.sub(r"<[^>]+>", " ", html)
    return ""


class GmailClient:
    """Thin async wrapper over the official Gmail API."""

    async def list_unread(self, max_results: int = 5) -> list[dict[str, str]]:
        def _call():
            service = _service()
            response = (
                service.users()
                .messages()
                .list(userId="me", q="is:unread", maxResults=max_results)
                .execute()
            )
            summaries = []
            for item in response.get("messages", []):
                full = (
                    service.users()
                    .messages()
                    .get(userId="me", id=item["id"], format="metadata",
                         metadataHeaders=["From", "Subject", "Date"])
                    .execute()
                )
                summaries.append(_metadata_to_summary(full))
            return summaries

        return await asyncio.to_thread(_call)

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        def _call():
            service = _service()
            response = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            summaries = []
            for item in response.get("messages", []):
                full = (
                    service.users()
                    .messages()
                    .get(userId="me", id=item["id"], format="metadata",
                         metadataHeaders=["From", "Subject", "Date"])
                    .execute()
                )
                summaries.append(_metadata_to_summary(full))
            return summaries

        return await asyncio.to_thread(_call)

    async def read(self, message_id: str) -> dict[str, str]:
        def _call():
            service = _service()
            full = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            summary = _metadata_to_summary(full)
            summary["body"] = _extract_plain_text(full.get("payload", {}))[:4000]
            return summary

        return await asyncio.to_thread(_call)

    async def send(self, to: str, subject: str, body: str) -> dict[str, str]:
        def _call():
            message = EmailMessage()
            message["To"] = to
            message["Subject"] = subject
            message.set_content(body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            sent = (
                _service().users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )
            return {"id": sent.get("id", ""), "to": to, "subject": subject}

        return await asyncio.to_thread(_call)


def _require_connected() -> None:
    if not gmail_oauth().is_authorized():
        raise ToolError(
            "Gmail is not connected yet. Say 'Elsyia, connect Gmail' and I will "
            "open Google's sign-in page for you to authorise your own account."
        )


class CheckGmailTool(Tool):
    name = "check_gmail"
    description = (
        "List unread inbox messages (sender, subject, snippet). "
        "Use when Aarya asks about new or unread email."
    )

    async def run(self, max_results: int = 5) -> dict[str, Any]:
        _require_connected()
        messages = await GmailClient().list_unread(max_results=min(max_results, 10))
        return {"unread": messages, "count": len(messages)}


class SearchGmailTool(Tool):
    name = "search_gmail"
    description = (
        "Search Aarya's Gmail with Gmail search operators "
        "(e.g. 'from:boss subject:report newer_than:7d')."
    )

    async def run(self, query: str, max_results: int = 5) -> dict[str, Any]:
        _require_connected()
        if not query or not query.strip():
            raise ToolError("A search query is required.")
        messages = await GmailClient().search(query.strip(), min(max_results, 10))
        return {"query": query.strip(), "results": messages, "count": len(messages)}


class ReadGmailTool(Tool):
    name = "read_gmail"
    description = "Read the plain-text body of one Gmail message by its id."

    async def run(self, message_id: str) -> dict[str, Any]:
        _require_connected()
        if not message_id or not message_id.strip():
            raise ToolError("A message id is required.")
        return await GmailClient().read(message_id.strip())


class SendGmailTool(Tool):
    name = "send_gmail"
    description = (
        "Send an email from Aarya's Gmail account. Requires confirmation "
        "because it acts on the outside world."
    )

    async def run(self, to: str, subject: str, body: str) -> dict[str, Any]:
        _require_connected()
        if not to or "@" not in to:
            raise ToolError("A valid recipient email address is required.")
        if not subject.strip():
            raise ToolError("An email subject is required.")
        if not body.strip():
            raise ToolError("An email body is required.")
        return await GmailClient().send(to.strip(), subject.strip(), body.strip())


class ConnectGmailTool(Tool):
    name = "connect_gmail"
    description = (
        "Start the one-time Google sign-in that connects Aarya's Gmail. "
        "Opens Google's consent page in his browser."
    )

    async def run(self) -> dict[str, str]:
        oauth = gmail_oauth()
        if oauth.is_authorized():
            return {"status": "already_connected"}
        await oauth.authorize_interactive()
        return {"status": "connected"}
