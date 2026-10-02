"""Local audit trail for assistant tool activity."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.core import get_logger, get_settings

logger = get_logger("tools.audit")
_lock = Lock()
_SENSITIVE_ARGUMENTS = {
    "path",
    "query",
    "content",
    "instruction",
    "title",
    "due_at",
    "application",
    "focus",
    "url",
    "session_id",
    "selector",
    "text",
    "value",
    "arguments",
    "image_path",
    "screenshot_path",
    "ocr_text",
    "region",
    "prompt",
}


def _redact_arguments(arguments: dict[str, Any] | None) -> dict[str, Any]:
    return {
        key: "<redacted>" if key in _SENSITIVE_ARGUMENTS else value
        for key, value in (arguments or {}).items()
    }


def record_tool_event(
    *,
    tool_name: str,
    status: str,
    arguments: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    """Append a redacted tool event to the configured local audit log."""
    settings = get_settings()
    log_path = Path(settings.LOG_FILE)
    if not log_path.is_absolute():
        log_path = Path(__file__).parents[4] / log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "status": status,
        "arguments": _redact_arguments(arguments),
        "result_status": (result or {}).get("status"),
    }
    try:
        with _lock:
            with log_path.open("a", encoding="utf-8") as audit_file:
                audit_file.write(json.dumps(event, default=str) + "\n")
    except OSError as exc:
        logger.warning("Could not write tool audit event: %s", exc)
