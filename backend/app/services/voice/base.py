"""
Base Voice Provider Interfaces

Abstract base classes for speech-to-text and text-to-speech providers.
Mirrors app.services.llm.base.LLMProvider — same Strategy pattern, so a
future STT/TTS provider swap follows the same shape as swapping LLMs.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class STTProvider(ABC):
    """Abstract base class for speech-to-text providers."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: Optional[str] = None) -> str:
        """
        Transcribe audio to text.

        Args:
            audio_bytes: Raw audio data (WAV/PCM — see provider docstring
                for the exact format each implementation expects).
            language: Optional ISO 639-1 language hint. None = auto-detect.

        Returns:
            Transcribed text.

        Raises:
            STTError: If transcription fails.
        """
        raise NotImplementedError


class TTSProvider(ABC):
    """Abstract base class for text-to-speech providers."""

    @abstractmethod
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Synthesize speech from text.

        Args:
            text: Text to speak.

        Yields:
            Audio data chunks (WAV) as they're generated, so playback can
            start before the full utterance is synthesized.

        Raises:
            TTSError: If synthesis fails.
        """
        raise NotImplementedError
        yield b""  # pragma: no cover — makes this an async generator for type checkers
