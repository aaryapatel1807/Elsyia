"""Print the effective latency-critical settings for diagnostics."""

from app.core import get_settings

settings = get_settings()
print(f"default_llm={settings.DEFAULT_LLM_PROVIDER}/{settings.DEFAULT_LLM_MODEL}")
print(f"embedding={settings.MEMORY_EMBEDDING_PROVIDER}/{settings.MEMORY_EMBEDDING_MODEL}")
print(f"whisper_beam={settings.WHISPER_BEAM_SIZE}")
print(f"voice_prewarm={settings.VOICE_PREWARM}")
print(f"piper_max_chars={settings.PIPER_MAX_CHARS}")
