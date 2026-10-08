"""Elsyia voice picker — choose Piper TTS voices, Jarvis-style.

API + config only (UI freeze: the overlay never changes). Everything here
is driven by the ``ELSYIA_TTS_VOICE`` setting and the ``/elsyia/voice/*``
endpoints.

Voices are Piper ``.onnx`` + ``.onnx.json`` pairs — free, local, downloaded
from HuggingFace (rhasspy/piper-voices). Switching is hot: no backend
restart needed. Downloads are explicit-only: nothing is ever fetched
unless the user asks via ``POST /elsyia/voice/download`` (the provider's own
first-run fetch for the *active* voice is the single exception, and it is
documented in the README).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from urllib.request import Request, urlopen

from app.core import TTSError, get_logger, get_settings
from app.services.elsyia.paths import elsyia_file
from app.services.voice.piper_tts import PiperTTSProvider

logger = get_logger("elsyia.voice_picker")

STATE_FILE = "voice.json"

# lang_REGION-name-quality, e.g. en_GB-alan-medium
VOICE_ID_RE = re.compile(r"^([a-z]{2})_([A-Z]{2})-([a-z0-9_]+)-(x_low|low|medium|high)$")

#: The Jarvis default — see README "Elsyia's voice" for why.
JARVIS_DEFAULT_VOICE = "en_GB-alan-medium"

#: Curated Piper English voices (rhasspy/piper-voices). Gender/quality notes
#: reflect each voice's public reputation; character is subjective — the
#: preview endpoint exists so Aarya can compare by ear.
VOICE_CATALOG: list[dict[str, str]] = [
    # --- Jarvis candidates: deep male voices ---
    {"id": "en_GB-alan-medium", "language": "English (British)", "gender": "male",
     "quality": "medium", "notes": "Deep British male — the Jarvis pick. Matches Elsyia's butler persona."},
    {"id": "en_US-ryan-medium", "language": "English (US)", "gender": "male",
     "quality": "medium", "notes": "Clear American male — the US alternative to alan."},
    {"id": "en_US-ryan-high", "language": "English (US)", "gender": "male",
     "quality": "high", "notes": "Higher-fidelity Ryan; heavier download."},
    {"id": "en_US-lessac-medium", "language": "English (US)", "gender": "male",
     "quality": "medium", "notes": "Previous Elsyia default; neutral American male."},
    {"id": "en_US-joe-medium", "language": "English (US)", "gender": "male",
     "quality": "medium", "notes": "Warm American male."},
    {"id": "en_US-bryce-medium", "language": "English (US)", "gender": "male",
     "quality": "medium", "notes": "American male, slightly brighter."},
    {"id": "en_US-john-medium", "language": "English (US)", "gender": "male",
     "quality": "medium", "notes": "Steady American male."},
    {"id": "en_US-sam-medium", "language": "English (US)", "gender": "male",
     "quality": "medium", "notes": "American male (CMU Arctic speaker)."},
    {"id": "en_US-danny-low", "language": "English (US)", "gender": "male",
     "quality": "low", "notes": "American male; low quality, smallest download."},
    {"id": "en_US-hfc_male-medium", "language": "English (US)", "gender": "male",
     "quality": "medium", "notes": "American male (HFC dataset)."},
    {"id": "en_GB-northern_english_male-medium", "language": "English (British)", "gender": "male",
     "quality": "medium", "notes": "British male, northern accent."},
    # --- Female alternatives ---
    {"id": "en_US-amy-medium", "language": "English (US)", "gender": "female",
     "quality": "medium", "notes": "Clear American female."},
    {"id": "en_US-kristin-medium", "language": "English (US)", "gender": "female",
     "quality": "medium", "notes": "American female."},
    {"id": "en_US-ljspeech-medium", "language": "English (US)", "gender": "female",
     "quality": "medium", "notes": "The classic LJSpeech female voice."},
    {"id": "en_GB-jenny_dioco-medium", "language": "English (British)", "gender": "female",
     "quality": "medium", "notes": "British female."},
]

PREVIEW_TEXT = "Good evening. I am Elsyia, at your service."


class VoiceNotAvailable(TTSError):
    """A voice id is unknown, malformed, or not downloaded."""


def normalize_voice_id(voice_id: str) -> str:
    """Trim and lower the region-insensitive parts of a voice id."""
    return (voice_id or "").strip()


def is_valid_voice_id(voice_id: str) -> bool:
    """True when the id matches Piper's lang_REGION-name-quality shape."""
    return bool(VOICE_ID_RE.match(normalize_voice_id(voice_id)))


def _models_dir() -> Path:
    settings = get_settings()
    path = Path(str(settings.PIPER_MODELS_DIR))
    if not path.is_absolute():
        # Relative to the backend package dir, mirroring existing behaviour.
        path = Path(__file__).resolve().parents[2] / path
    return path


def _state_path(explicit: Path | None = None) -> Path:
    return explicit if explicit is not None else elsyia_file(STATE_FILE)


def installed_voices(models_dir: Path | None = None) -> set[str]:
    """Voice ids with a complete .onnx + .onnx.json pair on disk."""
    directory = models_dir or _models_dir()
    found: set[str] = set()
    if directory.is_dir():
        for onnx in directory.glob("*.onnx"):
            if onnx.name.endswith(".onnx.json"):
                continue
            if (directory / f"{onnx.name}.json").exists():
                found.add(onnx.stem)
    return found


def resolve_active_voice(
    state_path: Path | None = None,
    models_dir: Path | None = None,
) -> str:
    """Effective voice: persisted choice > ELSYIA_TTS_VOICE > PIPER_VOICE.

    Falls back to the Jarvis default when nothing is configured.
    """
    _ = models_dir  # reserved for future per-voice validation
    try:
        raw = _state_path(state_path).read_text(encoding="utf-8")
        saved = (json.loads(raw) or {}).get("voice", "")
        if saved and is_valid_voice_id(saved):
            return normalize_voice_id(saved)
    except (OSError, ValueError):
        pass
    settings = get_settings()
    for candidate in (getattr(settings, "ELSYIA_TTS_VOICE", ""), settings.PIPER_VOICE):
        candidate = normalize_voice_id(str(candidate or ""))
        if candidate and is_valid_voice_id(candidate):
            return candidate
    return JARVIS_DEFAULT_VOICE


def list_voices(
    state_path: Path | None = None,
    models_dir: Path | None = None,
) -> dict[str, Any]:
    """Catalog merged with on-disk state: which voices exist, which is active."""
    directory = models_dir or _models_dir()
    installed = installed_voices(directory)
    active = resolve_active_voice(state_path, directory)
    catalog_ids = {entry["id"] for entry in VOICE_CATALOG}
    entries: list[dict[str, Any]] = []
    for entry in VOICE_CATALOG:
        vid = entry["id"]
        entries.append({
            **entry,
            "installed": vid in installed,
            "active": vid == active,
        })
    # Locally present voices that aren't in the curated catalog still show up.
    for vid in sorted(installed - catalog_ids):
        entries.append({
            "id": vid, "language": "unknown", "gender": "unknown",
            "quality": "unknown", "notes": "Found locally; not in the curated catalog.",
            "installed": True, "active": vid == active,
        })
    return {"active": active, "voices": entries}


def select_voice(voice_id: str, state_path: Path | None = None,
                 models_dir: Path | None = None) -> str:
    """Persist a new active voice. The id must already be downloaded.

    Hot-swap itself happens in the API layer via the voice factory, so this
    service stays free of import cycles.
    """
    vid = normalize_voice_id(voice_id)
    if not is_valid_voice_id(vid):
        raise VoiceNotAvailable(
            f"'{voice_id}' is not a Piper voice id (expected e.g. en_GB-alan-medium)."
        )
    if vid not in installed_voices(models_dir or _models_dir()):
        raise VoiceNotAvailable(
            f"Voice '{vid}' is not downloaded. Fetch it first with "
            f"POST /elsyia/voice/download, then select it."
        )
    path = _state_path(state_path)
    path.write_text(json.dumps({"voice": vid}, indent=2), encoding="utf-8")
    logger.info("Elsyia voice set to '%s' (persisted at %s)", vid, path)
    return vid


async def preview_wav(voice_id: str, text: str | None = None,
                      models_dir: Path | None = None) -> bytes:
    """Synthesize a sample line with a voice WITHOUT changing the active one."""
    vid = normalize_voice_id(voice_id)
    if not is_valid_voice_id(vid):
        raise VoiceNotAvailable(f"'{voice_id}' is not a Piper voice id.")
    directory = models_dir or _models_dir()
    if vid not in installed_voices(directory):
        raise VoiceNotAvailable(
            f"Voice '{vid}' is not downloaded — fetch it with "
            f"POST /elsyia/voice/download before previewing."
        )
    settings = get_settings()
    provider = PiperTTSProvider(voice=vid, models_dir=str(directory),
                                speed=settings.PIPER_SPEED)
    line = (text or PREVIEW_TEXT).strip() or PREVIEW_TEXT
    chunks = [chunk async for chunk in provider.synthesize(line)]
    return b"".join(chunks)


def voice_file_urls(voice_id: str) -> list[tuple[str, str]]:
    """(filename, URL) pairs for a Piper voice, mirroring the provider's layout."""
    vid = normalize_voice_id(voice_id)
    match = VOICE_ID_RE.match(vid)
    if not match:
        raise VoiceNotAvailable(f"'{voice_id}' is not a Piper voice id.")
    lang, lang_region, name, quality = match.groups()
    base = (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main"
        f"/{lang}/{lang_region}/{name}/{quality}"
    )
    return [
        (f"{vid}.onnx", f"{base}/{vid}.onnx"),
        (f"{vid}.onnx.json", f"{base}/{vid}.onnx.json"),
    ]


def download_voice(
    voice_id: str,
    models_dir: Path | None = None,
    progress_cb: Callable[[int, int | None, str], None] | None = None,
) -> Path:
    """Download a voice pair. Explicit-only — never called implicitly.

    Raises VoiceNotAvailable for bad ids and TTSError for fetch failures.
    """
    vid = normalize_voice_id(voice_id)
    if not is_valid_voice_id(vid):
        raise VoiceNotAvailable(f"'{voice_id}' is not a Piper voice id.")
    directory = models_dir or _models_dir()
    if vid in installed_voices(directory):
        raise VoiceNotAvailable(f"Voice '{vid}' is already downloaded.")
    directory.mkdir(parents=True, exist_ok=True)
    for filename, url in voice_file_urls(vid):
        dest = directory / filename
        if dest.exists():
            continue
        logger.info("Downloading Piper voice file %s …", url)
        req = Request(url, headers={"User-Agent": "elsyia-voice-picker"})
        try:
            with urlopen(req, timeout=300) as resp:
                total: int | None = None
                length = resp.headers.get("Content-Length")
                if length and length.isdigit():
                    total = int(length)
                downloaded = 0
                with open(dest, "wb") as fh:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total, filename)
        except VoiceNotAvailable:
            raise
        except Exception as exc:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise TTSError(f"Download of '{filename}' failed: {exc}") from exc
        logger.info("Saved %s", dest)
    return directory


async def download_voice_async(
    voice_id: str,
    models_dir: Path | None = None,
    progress_cb: Callable[[int, int | None, str], None] | None = None,
) -> Path:
    """Threaded wrapper so the event loop stays responsive during downloads."""
    return await asyncio.to_thread(download_voice, voice_id, models_dir, progress_cb)
