"""Jev screen-aware mode: "circle anything, then just ask".

Explicit-trigger vision Q&A over a local Ollama vision model
(moondream by default — `ollama pull moondream`).

PRIVACY INVARIANT — read before touching this module:
A screen capture enters the system ONLY through the user's explicit
region-select hotkey (Ctrl+Shift+S by default). There is no background
watching, no ambient screenshots, no periodic capture, and no code
path anywhere else that stores a capture. The capture lives in memory
with a short TTL, is answered against, and is discarded. Jev only
looks when you ask.
"""

from __future__ import annotations

import base64
import time
import uuid
from typing import Any

import httpx

from app.core import LLMError, get_logger, get_settings

logger = get_logger("jev.see")


class SeeUnavailable(Exception):
    """Raised when the vision pipeline cannot run (clean, catchable)."""


class SeeService:
    """In-memory current-capture store + local vision Q&A.

    Exactly one "current" capture exists at a time. It is written only
    by `store_capture` (called from POST /jev/see/capture, which the
    Electron shell calls after the user's explicit region select) and
    expires after JEV_SEE_CAPTURE_TTL_S.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.JEV_SEE_MODEL
        self._base_url = "http://localhost:11434"
        self._ttl_s = settings.JEV_SEE_CAPTURE_TTL_S
        self._capture: dict[str, Any] | None = None
        # Localhost only — proxy env vars must never interfere.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=2.0), trust_env=False
        )

    # --- capture store (explicit trigger only) ---

    def store_capture(self, png_bytes: bytes) -> dict[str, Any]:
        """Store a user-selected region capture. The ONLY write path."""
        if not png_bytes or not png_bytes.startswith(b"\x89PNG"):
            raise SeeUnavailable("Capture is not a valid PNG image.")
        capture_id = uuid.uuid4().hex[:12]
        self._capture = {
            "capture_id": capture_id,
            "png_bytes": png_bytes,
            "created_at": time.time(),
        }
        logger.info(f"Stored explicit screen capture {capture_id} ({len(png_bytes)} bytes)")
        return {"capture_id": capture_id, "bytes": len(png_bytes)}

    def _current(self, capture_id: str | None = None) -> dict[str, Any] | None:
        cap = self._capture
        if cap is None:
            return None
        if time.time() - cap["created_at"] > self._ttl_s:
            self._capture = None
            return None
        if capture_id and cap["capture_id"] != capture_id:
            return None
        return cap

    def has_capture(self) -> bool:
        return self._current() is not None

    def clear_capture(self) -> None:
        self._capture = None

    # --- vision ---

    async def _ollama_models(self) -> list[str]:
        try:
            resp = await self._client.get(f"{self._base_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []

    def _model_available(self, models: list[str]) -> bool:
        want = self._model.lower()
        return any(want == m.lower() or m.lower().startswith(want + ":") for m in models)

    async def status(self) -> dict[str, Any]:
        """Vision pipeline health: Ollama reachability + model presence."""
        models = await self._ollama_models()
        ollama_ok = True
        try:
            await self._client.get(f"{self._base_url}/api/tags")
        except Exception:
            ollama_ok = False
            models = []
        return {
            "vision_model": self._model,
            "model_available": self._model_available(models),
            "ollama_reachable": ollama_ok,
            "has_capture": self.has_capture(),
            "hotkey": get_settings().JEV_SEE_HOTKEY,
        }

    async def answer(self, question: str, capture_id: str | None = None) -> dict[str, Any]:
        """Ask a question about the current explicit capture.

        Raises SeeUnavailable when there is no capture or the vision
        model cannot run — callers turn this into a plain-spoken reply.
        """
        cap = self._current(capture_id)
        if cap is None:
            raise SeeUnavailable(
                "No screen capture yet — press Ctrl+Shift+S and select a region first."
            )
        started = time.perf_counter()
        models = await self._ollama_models()
        if not models:
            raise SeeUnavailable(
                "Ollama is not reachable. Start Ollama and try again."
            )
        if not self._model_available(models):
            raise SeeUnavailable(
                f"The vision model '{self._model}' is not pulled yet. "
                f"Run `ollama pull {self._model}` once, then ask again."
            )
        b64 = base64.b64encode(cap["png_bytes"]).decode("ascii")
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "You are Jev, a helpful desktop assistant. Answer the "
                        "question about the attached screen capture concisely, "
                        "in plain spoken style, no markdown headers. If the "
                        "question cannot be answered from the image, say so "
                        "plainly instead of guessing.\n\n"
                        f"Question: {question}"
                    ),
                    "images": [b64],
                }
            ],
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.2, "num_predict": 256},
        }
        try:
            resp = await self._client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = (data.get("message") or {}).get("content", "").strip()
        except httpx.TimeoutException as exc:
            raise SeeUnavailable("The vision model timed out — try a smaller region.") from exc
        except Exception as exc:
            raise SeeUnavailable(f"Vision request failed: {exc}") from exc
        total_ms = int((time.perf_counter() - started) * 1000)
        if not text:
            raise SeeUnavailable("The vision model returned an empty answer.")
        return {
            "answer": text,
            "capture_id": cap["capture_id"],
            "model": self._model,
            "timings_ms": {"vision_ms": total_ms, "total_ms": total_ms},
        }


_see_service: SeeService | None = None


def get_see_service() -> SeeService:
    """Process-wide singleton (mirrors the wakeword/agent services)."""
    global _see_service
    if _see_service is None:
        _see_service = SeeService()
    return _see_service
