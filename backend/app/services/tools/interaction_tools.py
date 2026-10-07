"""Interaction primitives: tools that talk back to Aarya mid-flow."""

from __future__ import annotations

from typing import Any

from app.services.tools.base import Tool, ToolError


class AskUserTool(Tool):
    """Ask Aarya a clarifying question and wait for the answer.

    In agent mode the runner intercepts this tool: the plan pauses with
    status "awaiting_input" and resumes when the answer arrives via
    POST /jev/agent/{plan_id}/confirm with {"user_input": "..."} — the
    answer is threaded into later steps as the step result.
    In a single turn the question is simply spoken back.
    """

    name = "ask_user"
    description = (
        "Ask Aarya a clarifying question when a task cannot proceed "
        "without a choice only they can make. "
        'Args: {"question": "<the question>"}. '
        "Use sparingly — one clear question at a time."
    )

    async def run(self, question: str = "") -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            raise ToolError("ask_user needs a question to ask.")
        return {"question": question, "awaiting_answer": True}
