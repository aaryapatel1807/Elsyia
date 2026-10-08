"""Elsyia — Aarya's personal desktop butler.

The central assistant persona of Elysia: a real-time voice/text loop
(hotkey -> mic -> Whisper -> Ollama -> actions -> TTS) with full local
system capabilities and app integrations. Everything is local-first and
free; no paid APIs, no cloud keys.
"""

from app.services.elsyia.loop import ElsyiaLoop, ElsyiaTurnResult, get_elsyia_loop
from app.services.elsyia.persona import ELSYIA_NAME, build_system_prompt, load_persona

__all__ = [
    "ELSYIA_NAME",
    "ElsyiaLoop",
    "ElsyiaTurnResult",
    "build_system_prompt",
    "get_elsyia_loop",
    "load_persona",
]
