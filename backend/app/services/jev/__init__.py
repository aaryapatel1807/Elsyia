"""Jev — Aarya's personal desktop butler.

The central assistant persona of Elysia: a real-time voice/text loop
(hotkey -> mic -> Whisper -> Ollama -> actions -> TTS) with full local
system capabilities and app integrations. Everything is local-first and
free; no paid APIs, no cloud keys.
"""

from app.services.jev.loop import JevLoop, JevTurnResult, get_jev_loop
from app.services.jev.persona import JEV_NAME, build_system_prompt, load_persona

__all__ = [
    "JEV_NAME",
    "JevLoop",
    "JevTurnResult",
    "build_system_prompt",
    "get_jev_loop",
    "load_persona",
]
