"""
Whisper STT Provider

Speech-to-text using faster-whisper (CTranslate2-based Whisper inference —
significantly faster and lighter than the reference openai-whisper
implementation, and runs fine on CPU, which matters for a ₹0-budget
desktop app with no guaranteed GPU).
"""

import asyncio
import io
from typing import Optional

from app.core import STTError, get_logger
from app.services.voice.base import STTProvider

logger = get_logger("voice.whisper")


class WhisperSTTProvider(STTProvider):
    """
    STT provider backed by faster-whisper.

    The model is loaded once and reused across requests — model load is
    the expensive part (seconds), actual transcription of a few seconds
    of push-to-talk audio is fast.
    """

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8", beam_size: int = 1) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._model = None  # lazy-loaded on first use
        self._load_lock = asyncio.Lock()

    async def _load_model(self):
        async with self._load_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise STTError(
                        "faster-whisper is not installed. Run `pip install faster-whisper` "
                        "(or `uv sync`) in the backend environment."
                    ) from exc

                logger.info(
                    f"Loading Whisper model '{self._model_size}' "
                    f"(device={self._device}, compute_type={self._compute_type})"
                )
                self._model = WhisperModel(
                    self._model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                )
        return self._model

    async def warmup(self) -> None:
        """Load the Whisper model without transcribing user audio."""
        await self._load_model()

    async def transcribe(self, audio_bytes: bytes, language: Optional[str] = None) -> str:
        """
        Transcribe audio bytes (WAV) to text.

        faster-whisper's transcribe() is synchronous/CPU-bound, so it runs
        in a thread to avoid blocking the event loop.
        """
        if not audio_bytes:
            raise STTError("No audio data provided.")

        model = await self._load_model()
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self._transcribe_sync, model, audio_bytes, language)
        except STTError:
            raise
        except Exception as exc:
            logger.error(f"Whisper transcription failed: {exc}")
            raise STTError(f"Transcription failed: {exc}") from exc

    def _transcribe_sync(self, model, audio_bytes: bytes, language: Optional[str]) -> str:
        logger.info(f"Whisper input: {len(audio_bytes)} bytes audio data")
        
        # Force English if no language is specified to prevent noise from 
        # being hallucinated as Welsh, Urdu, etc.
        if not language:
            language = "en"
            
        segments, info = model.transcribe(
            io.BytesIO(audio_bytes),
            language=language,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=self._beam_size,
        )
        
        text = " ".join(segment.text.strip() for segment in segments).strip()
        logger.info(f"Whisper output: '{text}' (length={len(text)}), duration={info.duration:.2f}s, language={info.language}")
        return text
