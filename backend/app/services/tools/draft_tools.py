"""Draft generation tool for unsent local text."""

from __future__ import annotations

from typing import Any

from app.core import get_settings
from app.services.llm.factory import create_llm_provider
from app.services.tools.base import Tool, ToolError


class DraftTextTool(Tool):
    name = "draft_text"
    description = (
        "Draft an email, message, note, or other text from a user instruction. "
        "The result is returned locally and is never sent automatically."
    )

    async def run(self, instruction: str, tone: str = "clear and natural") -> dict[str, Any]:
        cleaned_instruction = " ".join(instruction.strip().split())
        if len(cleaned_instruction) < 3:
            raise ToolError("Draft instruction must contain at least three characters.")
        settings = get_settings()
        if len(cleaned_instruction) > 2000:
            cleaned_instruction = cleaned_instruction[:2000]
        cleaned_tone = " ".join(tone.strip().split())[:120] or "clear and natural"
        prompt = (
            "Write a polished draft based on the user's instruction. Do not claim that it was sent, "
            "do not add a subject unless requested, and return only the draft text.\n\n"
            f"Tone: {cleaned_tone}\n"
            f"Instruction: {cleaned_instruction}"
        )
        try:
            provider = create_llm_provider(settings.DEFAULT_LLM_PROVIDER)
            chunks: list[str] = []
            async for token in provider.generate(
                [
                    {
                        "role": "system",
                        "content": "You are Elysia's concise local drafting assistant.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=384,
            ):
                chunks.append(token)
        except Exception as exc:
            raise ToolError("The configured local model could not create the draft.") from exc
        draft = "".join(chunks).strip()
        if not draft:
            raise ToolError("The drafting model returned an empty result.")
        truncated = len(draft) > settings.TOOLS_MAX_DRAFT_CHARS
        if truncated:
            draft = draft[: settings.TOOLS_MAX_DRAFT_CHARS].rstrip()
        return {
            "draft": draft,
            "tone": cleaned_tone,
            "characters": len(draft),
            "truncated": truncated,
            "sent": False,
        }
