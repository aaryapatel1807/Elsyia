"""Jev dictation mode: say it, it types.

A separate mode from the assistant loop — dictation types text into the
currently focused application and stays silent. It never triggers Jev's
spoken replies, and the caller is expected to pause the wake-word listener
while dictating so Jev can't hear itself.

Pipeline: mic audio -> Whisper STT -> Ollama "instant cleanup" pass ->
pynput keyboard injection (typed, not pasted, so it works in every app:
Gmail, Docs, Notion, chat boxes, terminals).

Everything runs on-device: faster-whisper and Ollama are both local.
No audio is stored after the turn.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.core import get_logger, get_settings

logger = get_logger("jev.dictation")


class DictationUnavailable(Exception):
    """Dictation can't run on this machine (missing optional dependency)."""


_DEFAULT_CLEANUP_PROMPT = """You are a dictation cleanup engine. Rewrite the spoken transcript below as clean written text a person would be happy to send as-is.

Rules:
- Remove filler words (um, uh, er, like, you know, basically) unless they carry meaning.
- Fix punctuation, capitalisation, and obvious speech-recognition mishears using context.
- Resolve self-corrections: keep ONLY the final intended version.
  Example: "meet at 2... no, 3pm" becomes "Meet at 3pm."
- Preserve the speaker's language — if they speak Hindi/Hinglish, keep it; do not translate.
- Preserve the speaker's meaning exactly. Do not add content, do not answer questions, do not explain yourself.
- Output ONLY the cleaned text. No quotes around it, no preamble.

Transcript:
{transcript}
"""


def load_cleanup_prompt() -> str:
    """Load the cleanup prompt from prompts/, falling back to the embedded copy."""
    here = Path(__file__).resolve()
    # backend/app/services/jev/dictation.py -> repo root is 4 levels up
    candidates = [
        here.parents[4] / "prompts" / "dictation-cleanup.txt",
        Path.cwd() / "prompts" / "dictation-cleanup.txt",
    ]
    for path in candidates:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return _DEFAULT_CLEANUP_PROMPT


def _pynput_available() -> bool:
    try:
        import pynput  # noqa: F401
        import pynput.keyboard  # noqa: F401
    except ImportError:
        return False
    return True


async def cleanup_transcript(raw: str, settings: Any | None = None) -> str:
    """Run the Ollama "instant cleanup" pass over a raw STT transcript.

    Strips filler words, fixes punctuation/mishears, and resolves
    self-corrections ("meet at 2... no, 3pm" -> "Meet at 3pm.").
    Returns "" for empty input. Unit-testable: the LLM provider is the
    only external call.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    settings = settings or get_settings()
    from app.services.llm.factory import get_llm_provider

    provider = get_llm_provider(settings.DEFAULT_LLM_PROVIDER)
    prompt = load_cleanup_prompt().replace("{transcript}", raw)
    chunks: list[str] = []
    async for chunk in provider.generate(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=600,
    ):
        chunks.append(chunk)
    cleaned = "".join(chunks).strip()
    # Guard against chatty models wrapping the answer in quotes.
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()
    return cleaned


def type_text(text: str) -> int:
    """Type text into the currently focused application, character by character.

    Typed (not pasted) so it works in every app, including terminals and
    chat boxes that ignore clipboard pastes. Returns the number of
    characters typed. Raises DictationUnavailable when pynput is missing.
    """
    if not text:
        return 0
    try:
        from pynput.keyboard import Controller
    except ImportError as exc:
        raise DictationUnavailable(
            "Typing needs the 'pynput' package (pip install pynput)."
        ) from exc
    keyboard = Controller()
    # Type in chunks so very long dictations stay reliable.
    for i in range(0, len(text), 400):
        keyboard.type(text[i : i + 400])
    logger.info(f"Dictation typed {len(text)} chars into the focused app")
    return len(text)


async def type_text_async(text: str) -> int:
    """Non-blocking wrapper for type_text (pynput is synchronous)."""
    return await asyncio.to_thread(type_text, text)


def dictation_status() -> dict[str, Any]:
    """Capability report for the dictation settings UI."""
    settings = get_settings()
    return {
        "hotkey": settings.JEV_DICTATION_HOTKEY,
        "confirm": settings.JEV_DICTATION_CONFIRM,
        "typing_available": _pynput_available(),
        "on_device": True,
    }
