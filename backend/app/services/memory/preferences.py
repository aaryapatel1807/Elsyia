"""Background extraction of explicit, stable user preferences."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Optional

from app.core import get_logger, get_settings
from app.services.memory import get_memory_store

logger = get_logger("memory.preferences")


@dataclass(frozen=True)
class PreferenceCandidate:
    """A safe candidate extracted from an explicit user statement."""

    content: str
    category: str
    confidence: float


_PATTERNS: tuple[tuple[re.Pattern[str], str, float, str], ...] = (
    (
        re.compile(r"\b(?:i|i'm|i am) prefer(?:s)?\s+(.+?)[.!?]?$", re.IGNORECASE),
        "preference",
        0.96,
        "The user explicitly stated a preference.",
    ),
    (
        re.compile(r"\bmy favorite (?:is|are)\s+(.+?)[.!?]?$", re.IGNORECASE),
        "preference",
        0.94,
        "The user explicitly stated a favorite.",
    ),
    (
        re.compile(r"\bremember that\s+(.+?)[.!?]?$", re.IGNORECASE),
        "fact",
        0.99,
        "The user explicitly requested memory.",
    ),
    (
        re.compile(r"\bcall me\s+(.+?)[.!?]?$", re.IGNORECASE),
        "identity",
        0.98,
        "The user explicitly provided a preferred name.",
    ),
)
_SECRET_RE = re.compile(r"\b(password|passcode|api key|token|secret|private key|credential)\b", re.IGNORECASE)


def extract_candidates(user_message: str) -> list[PreferenceCandidate]:
    """Extract only explicit stable preferences or facts from one message."""
    text = " ".join(user_message.strip().split())
    if not text or "?" in text[:-1] or _SECRET_RE.search(text):
        return []

    candidates: list[PreferenceCandidate] = []
    for pattern, category, confidence, reason in _PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        value = " ".join(match.group(1).split()).strip(" .,!?:;")
        if len(value) < 2 or len(value) > 250:
            continue
        if value.lower() in {"to", "that", "this", "it"}:
            continue
        if category == "preference":
            content = f"The user prefers {value}."
        elif category == "identity":
            content = f"The user prefers to be called {value}."
        else:
            content = value[0].upper() + value[1:]
            if not content.endswith("."):
                content += "."
        candidates.append(PreferenceCandidate(content, category, confidence))
    return candidates


def _is_duplicate(content: str, scope: str) -> bool:
    normalized = " ".join(content.lower().split()).rstrip(".")
    return any(
        " ".join(record.content.lower().split()).rstrip(".") == normalized
        for record in get_memory_store().list(scope=scope, limit=200, include_pending=True)
    )


def persist_candidates(candidates: list[PreferenceCandidate], scope: str = "default") -> int:
    """Persist non-duplicate safe candidates and return the number saved."""
    settings = get_settings()
    if not settings.ENABLE_MEMORY:
        return 0
    saved = 0
    for candidate in candidates:
        if candidate.confidence < 0.9 or _is_duplicate(candidate.content, scope):
            continue
        get_memory_store().save(
            candidate.content,
            scope=scope,
            category=candidate.category,
            source="background",
            approved=False,
        )
        saved += 1
    return saved


async def _extract_and_persist(user_message: str, scope: str) -> None:
    """Run extraction off the chat response path."""
    try:
        candidates = await asyncio.to_thread(extract_candidates, user_message)
        if candidates:
            saved = await asyncio.to_thread(persist_candidates, candidates, scope)
            if saved:
                logger.info("Saved %s background preference memories", saved)
    except Exception as exc:
        logger.warning("Background preference extraction skipped: %s", exc)


def schedule_preference_extraction(user_message: str, scope: str = "default") -> Optional[asyncio.Task[None]]:
    """Schedule safe extraction without blocking the current chat response."""
    settings = get_settings()
    if not settings.ENABLE_MEMORY or not settings.ENABLE_PREFERENCE_EXTRACTION:
        return None
    try:
        return asyncio.create_task(_extract_and_persist(user_message, scope))
    except RuntimeError:
        logger.debug("No active event loop; preference extraction skipped")
        return None
