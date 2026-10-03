"""
Piper TTS Provider

Text-to-speech using Piper (fast, local, neural TTS — no API key, runs on
CPU). Piper distributes voices as separate `.onnx` model + `.onnx.json`
config file pairs that must be downloaded once and placed in
PIPER_MODELS_DIR (see app.core.config.Settings.PIPER_MODELS_DIR); Piper
itself is not bundled with model weights.
"""

import asyncio
import io
import wave
from pathlib import Path
from typing import AsyncGenerator

from app.core import TTSError, get_logger
from app.services.voice.base import TTSProvider

logger = get_logger("voice.piper")


class PiperTTSProvider(TTSProvider):
    """
    TTS provider backed by Piper.

    Synthesis is CPU-bound and synchronous under the hood, so it's run in
    a thread. The result is chunked into a single WAV yield for now —
    true incremental streaming can be added later by chunking Piper's
    per-sentence output instead of waiting for the whole utterance.
    """

    def __init__(self, voice: str, models_dir: str, speed: float = 1.0) -> None:
        self._voice_name = voice
        self._models_dir = Path(models_dir)
        self._speed = speed
        self._voice = None  # lazy-loaded on first use
        self._load_lock = asyncio.Lock()

    async def _load_voice(self):
        async with self._load_lock:
            if self._voice is None:
                try:
                    from piper import PiperVoice
                except ImportError as exc:
                    raise TTSError(
                        "piper-tts is not installed. Run `pip install piper-tts` "
                        "(or `uv sync`) in the backend environment."
                    ) from exc

                model_path = self._models_dir / f"{self._voice_name}.onnx"
                config_path = self._models_dir / f"{self._voice_name}.onnx.json"
                if not model_path.exists() or not config_path.exists():
                    logger.info(
                        "Piper voice '%s' not found in %s — downloading (first run)…",
                        self._voice_name,
                        self._models_dir,
                    )
                    try:
                        await asyncio.to_thread(self._download_voice_files, model_path, config_path)
                    except Exception as exc:
                        raise TTSError(
                            f"Piper voice files not found for '{self._voice_name}' in "
                            f"{self._models_dir}, and the automatic download failed "
                            f"({exc}). Download the .onnx and .onnx.json pair from "
                            "the Piper voices repo and place them there."
                        ) from exc

                logger.info(f"Loading Piper voice '{self._voice_name}' from {self._models_dir}")
                self._voice = PiperVoice.load(str(model_path), config_path=str(config_path))
        return self._voice

    def _download_voice_files(self, model_path: Path, config_path: Path) -> None:
        """Download a Piper voice pair from the official voices repo (HuggingFace).

        Voice names look like ``en_US-lessac-medium`` which maps to
        ``…/en/en_US/lessac/medium/en_US-lessac-medium.onnx``. Runs in a
        worker thread; raises on any failure.
        """
        import urllib.request

        parts = self._voice_name.split("-")
        if len(parts) != 3:
            raise TTSError(
                f"Cannot derive a download URL from voice name '{self._voice_name}' "
                "(expected e.g. en_US-lessac-medium)."
            )
        lang_region, name, quality = parts
        lang = lang_region.split("_")[0].lower()
        base = (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main"
            f"/{lang}/{lang_region}/{name}/{quality}"
        )
        self._models_dir.mkdir(parents=True, exist_ok=True)
        for dest, url in (
            (model_path, f"{base}/{self._voice_name}.onnx"),
            (config_path, f"{base}/{self._voice_name}.onnx.json"),
        ):
            if dest.exists():
                continue
            logger.info("Downloading Piper voice file %s …", url)
            req = urllib.request.Request(url, headers={"User-Agent": "jev-voice-setup"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as fh:
                fh.write(resp.read())
            logger.info("Saved %s", dest)

    async def warmup(self) -> None:
        """Load the Piper voice model without synthesizing user text."""
        await self._load_voice()

    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesize text to a single WAV byte payload."""
        if not text.strip():
            raise TTSError("No text provided to synthesize.")

        voice = await self._load_voice()
        loop = asyncio.get_running_loop()
        try:
            wav_bytes = await loop.run_in_executor(None, self._synthesize_sync, voice, text)
        except TTSError:
            raise
        except Exception as exc:
            logger.error(f"Piper synthesis failed: {exc}")
            raise TTSError(f"Synthesis failed: {exc}") from exc

        yield wav_bytes

    def _synthesize_sync(self, voice, text: str) -> bytes:
        from piper import SynthesisConfig

        syn_config = SynthesisConfig(length_scale=1.0 / self._speed)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, syn_config=syn_config)
        return buffer.getvalue()