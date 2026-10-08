"""Screen-aware tool: answer questions about the user's explicit capture.

`see_capture` is the agent-mode bridge for screen-aware mode. It does
NOT take screenshots — it only reads the single in-memory capture that
the user created moments ago with the region-select hotkey
(Ctrl+Shift+S). If no capture exists, it says so plainly instead of
guessing. Read-only: never confirmation-gated, because the capture
itself was the user's explicit act.
"""

from __future__ import annotations

from typing import Any

from app.services.elsyia.see import SeeUnavailable, get_see_service
from app.services.tools.base import Tool, ToolError


class SeeCaptureTool(Tool):
    name = "see_capture"
    description = (
        "Answer a question about the user's current screen capture. "
        "A capture exists ONLY right after the user pressed the "
        "screen-capture hotkey (Ctrl+Shift+S) and selected a region — "
        "there is no other way a capture comes to exist, and Elsyia never "
        "screenshots in the background. Use when the user refers to "
        "'this', 'here', 'the screen', 'this error', or 'what's this'. "
        "If no capture exists, the tool says so — relay that plainly "
        "and ask them to capture first."
    )

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        if not question or not question.strip():
            raise ToolError("A question about the capture is required.")
        try:
            result = await get_see_service().answer(question.strip())
        except SeeUnavailable as exc:
            raise ToolError(str(exc)) from exc
        return {
            "status": "completed",
            "answer": result["answer"],
            "capture_id": result["capture_id"],
            "local_only": True,
        }
