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
                voice=settings.PIPER_VOICE,
                models_dir=settings.PIPER_MODELS_DIR,
                speed=settings.PIPER_SPEED,
            )
        else:
            raise ConfigurationError(f"Unknown TTS provider: {provider}", details={"provider": provider})
    
    return _tts_providers[provider]


# Deprecated aliases for backward compatibility
def create_stt_provider(provider: Literal["whisper"] = "whisper") -> STTProvider:
    """Deprecated: use get_stt_provider() instead."""
    return get_stt_provider(provider)


def create_tts_provider(provider: Literal["piper"] = "piper") -> TTSProvider:
    """Deprecated: use get_tts_provider() instead."""
    return get_tts_provider(provider)
