"""Fast local vector embeddings for memory retrieval.

This dependency-free embedder uses hashed word, word-pair, and character n-gram
features. It is deterministic, local, and replaceable by a neural embedding
provider later without changing the memory API.
"""

from __future__ import annotations

import hashlib
import math
import re

import httpx

from app.core import get_logger, get_settings

logger = get_logger("memory.embeddings")

_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")
_DIMENSIONS = 256
_ALIASES = {
    "short": "concise",
    "brief": "concise",
    "voice": "spoken",
    "audio": "spoken",
    "reply": "answer",
    "replies": "answers",
    "response": "answer",
    "responses": "answers",
}


def _bucket(feature: str) -> int:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little") % _DIMENSIONS


def embed_text(text: str) -> list[float]:
    """Return a normalized local vector for one text string."""
    normalized = " ".join(text.lower().split())
    tokens = [_ALIASES.get(token, token) for token in _TOKEN_RE.findall(normalized)]
    vector = [0.0] * _DIMENSIONS

    for token in tokens:
        vector[_bucket("w:" + token)] += 1.0
        padded = f"^{token}$"
        for index in range(max(0, len(padded) - 2)):
            vector[_bucket("c:" + padded[index : index + 3])] += 0.15

    for first, second in zip(tokens, tokens[1:]):
        vector[_bucket(f"b:{first}:{second}")] += 0.5

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def neural_embed_text(text: str) -> list[float] | None:
    """Request a neural embedding from the local Ollama embedding model."""
    settings = get_settings()
    if settings.MEMORY_EMBEDDING_PROVIDER != "ollama":
        return None
    try:
        response = httpx.post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed",
            json={
                "model": settings.MEMORY_EMBEDDING_MODEL,
                "input": text,
                "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            },
            timeout=settings.MEMORY_EMBEDDING_TIMEOUT_MS / 1000,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if embeddings and isinstance(embeddings[0], list):
            return [float(value) for value in embeddings[0]]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.debug("Neural embedding unavailable; using local fallback: %s", exc)
    return None


def prewarm_neural_embedding() -> bool:
    """Load the neural embedding model in a background startup task."""
    settings = get_settings()
    if settings.MEMORY_EMBEDDING_PROVIDER != "ollama":
        return False
    try:
        response = httpx.post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/embed",
            json={
                "model": settings.MEMORY_EMBEDDING_MODEL,
                "input": "warmup",
                "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            },
            timeout=max(30.0, settings.MEMORY_EMBEDDING_TIMEOUT_MS / 1000),
        )
        response.raise_for_status()
        return bool(response.json().get("embeddings"))
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Neural embedding prewarm skipped: %s", exc)
        return False


def embed_for_memory(text: str) -> list[float]:
    """Use neural embeddings when available, otherwise use the local fallback."""
    return neural_embed_text(text) or embed_text(text)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Calculate cosine similarity for two normalized or unnormalized vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
