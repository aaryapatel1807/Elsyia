"""Elsyia persona prompt loading."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

ELSYIA_NAME = "Elsyia"

_PROMPT_PATH = Path(__file__).resolve().parents[4] / "prompts" / "elsyia.txt"


@lru_cache(maxsize=1)
def load_persona() -> str:
    """Load the Elsyia persona prompt from disk (cached)."""
    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_system_prompt(user_name: str = "Aarya") -> str:
    """Build the full system prompt: persona + live date/time context."""
    now = datetime.now().astimezone()
    context = (
        f"You are speaking with {user_name}. "
        f"The current date and time is {now.strftime('%A, %d %B %Y, %I:%M %p %Z')}."
    )
    return f"{load_persona()}\n\n{context}"
