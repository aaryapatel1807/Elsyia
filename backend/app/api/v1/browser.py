"""REST API for the read-only browser foundation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.models import (
    BrowserDownloadRequest,
    BrowserNavigateRequest,
    BrowserScreenshotRequest,
    BrowserSessionRequest,
)
from app.services.tools import registry
from app.services.tools.audit import record_tool_event

router = APIRouter()


def _result_dict(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "tool_name": result.tool_name,
        "result": result.result,
        "error": result.error,
        "confirmation_required": result.confirmation_required,
        "confirmation_message": result.confirmation_message,
        "metadata": result.metadata,
    }


async def _execute(
    tool_name: str, arguments: dict[str, Any], *, confirmed: bool = False
) -> dict[str, Any]:
    result = await registry.execute(tool_name, arguments, confirmed=confirmed)
    payload = _result_dict(result)
    record_tool_event(tool_name=tool_name, status=result.status, arguments=arguments, result=payload)
    return payload


@router.post("/navigate")
async def navigate(request: BrowserNavigateRequest) -> dict[str, Any]:
    """Create an isolated session and navigate to a trusted URL."""
    return await _execute("navigate_browser", {"url": request.url})


@router.get("/session/{session_id}")
async def session_info(session_id: str) -> dict[str, Any]:
    """Return metadata for one active browser session."""
    return await _execute("browser_session_info", {"session_id": session_id})


@router.post("/session/{session_id}/scrape")
async def scrape(session_id: str) -> dict[str, Any]:
    """Extract bounded visible page content from one active session."""
    return await _execute("scrape_browser_page", {"session_id": session_id})


@router.post("/session/{session_id}/screenshot")
async def screenshot(request: BrowserScreenshotRequest) -> dict[str, Any]:
    """Capture the visible viewport after explicit confirmation."""
    return await _execute(
        "screenshot_browser_page",
        {"session_id": request.session_id},
        confirmed=request.confirmed,
    )


@router.post("/session/{session_id}/download")
async def download(request: BrowserDownloadRequest) -> dict[str, Any]:
    """Download one same-origin file after explicit confirmation."""
    return await _execute(
        "download_browser_file",
        {"session_id": request.session_id, "url": request.url},
        confirmed=request.confirmed,
    )


@router.post("/session/{session_id}/close")
async def close(session_id: str) -> dict[str, Any]:
    """Close an isolated browser session."""
    return await _execute("close_browser_session", {"session_id": session_id})
