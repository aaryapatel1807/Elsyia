"""
Voice Provider Factory

Creates STT/TTS provider instances based on configuration.
Mirrors app.services.llm.factory.create_llm_provider.
"""

from typing import Literal

from app.core import ConfigurationError, get_logger, get_settings
from app.services.voice.base import STTProvider, TTSProvider
from app.services.voice.piper_tts import PiperTTSProvider
from app.services.voice.whisper_stt import WhisperSTTProvider
from app.services.jev.voice_picker import resolve_active_voice

logger = get_logger("voice.factory")

# Cached provider instances (singletons per provider type)
_stt_providers: dict[str, STTProvider] = {}
_tts_providers: dict[str, TTSProvider] = {}


def get_stt_provider(provider: Literal["whisper"] = "whisper") -> STTProvider:
    """
    Get or create the STT provider instance (cached).

    Args:
        provider: Provider name. Only "whisper" exists today.

    Returns:
        Configured STT provider instance.
    """
    global _stt_providers
    
    if provider not in _stt_providers:
        settings = get_settings()
        logger.info(f"Creating STT provider: {provider}")
        if provider == "whisper":
            _stt_providers[provider] = WhisperSTTProvider(
                model_size=settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
                beam_size=settings.WHISPER_BEAM_SIZE,
            )
        else:
            raise ConfigurationError(f"Unknown STT provider: {provider}", details={"provider": provider})
    
    return _stt_providers[provider]


def get_tts_provider(provider: Literal["piper"] = "piper") -> TTSProvider:
    """
    Get or create the TTS provider instance (cached).

    Args:
        provider: Provider name. Only "piper" exists today.

    Returns:
        Configured TTS provider instance.
    """
    global _tts_providers
    
    if provider not in _tts_providers:
        settings = get_settings()
        logger.info(f"Creating TTS provider: {provider}")
        if provider == "piper":
            _tts_providers[provider] = PiperTTSProvider(
                voice=resolve_active_voice(),
                models_dir=settings.PIPER_MODELS_DIR,
                speed=settings.PIPER_SPEED,
            )
        else:
            raise ConfigurationError(f"Unknown TTS provider: {provider}", details={"provider": provider})
    
    return _tts_providers[provider]


def set_tts_voice(voice: str) -> TTSProvider:
    """Hot-swap the cached Piper provider to a new voice — no restart needed.

    In-flight syntheses keep their old provider instance; every later
    get_tts_provider() call returns the new voice.
    """
    settings = get_settings()
    logger.info(f"Hot-swapping TTS voice to: {voice}")
    _tts_providers["piper"] = PiperTTSProvider(
        voice=voice,
        models_dir=settings.PIPER_MODELS_DIR,
        speed=settings.PIPER_SPEED,
    )
    return _tts_providers["piper"]


# Deprecated aliases for backward compatibility
def create_stt_provider(provider: Literal["whisper"] = "whisper") -> STTProvider:
    """Deprecated: use get_stt_provider() instead."""
    return get_stt_provider(provider)


def create_tts_provider(provider: Literal["piper"] = "piper") -> TTSProvider:
    """Deprecated: use get_tts_provider() instead."""
    return get_tts_provider(provider)
