"""Jev wake-word listener: hands-free summoning ("hey Jev").

A tiny always-on keyword spotter (openWakeWord, local ONNX inference) that
idles on the microphone watching ONLY for the wake phrase. On detection it
raises a wake event, pauses itself for a cooldown (so Jev's own spoken
reply can't re-trigger it), and the Electron shell summons the Jev overlay
and starts the normal /jev/turn voice loop. When the turn finishes, the
overlay resumes the listener and it goes back to sleep.

Privacy: no audio ever leaves the machine. The mic stream is scored
on-device in 80 ms frames and discarded immediately; nothing is recorded,
stored, or transmitted.

The listener is OFF by default and only runs after an explicit opt-in
(the overlay's wake-word toggle or JEV_WAKE_ENABLED=true).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core import get_logger, get_settings
from app.services.jev.paths import jev_data_dir

logger = get_logger("jev.wakeword")

SAMPLE_RATE = 16_000
CHUNK_SAMPLES = 1280  # 80 ms frames — openWakeWord's native frame size
DEFAULT_MODEL_NAME = "hey_jarvis"  # community model, works out of the box
STATE_FILE = "wakeword.json"


class WakeWordUnavailable(Exception):
    """Raised when the listener can't run on this machine (no model lib / mic)."""


@dataclass
class WakeWordConfig:
    enabled: bool = False
    model: str = DEFAULT_MODEL_NAME  # openWakeWord model name or path to .onnx/.tflite
    threshold: float = 0.5
    cooldown_s: int = 45

    @classmethod
    def from_settings(cls) -> "WakeWordConfig":
        settings = get_settings()
        return cls(
            enabled=bool(getattr(settings, "JEV_WAKE_ENABLED", False)),
            model=str(getattr(settings, "JEV_WAKE_MODEL", DEFAULT_MODEL_NAME) or DEFAULT_MODEL_NAME),
            threshold=float(getattr(settings, "JEV_WAKE_THRESHOLD", 0.5)),
            cooldown_s=int(getattr(settings, "JEV_WAKE_COOLDOWN_S", 45)),
        )


def wakeword_models_dir() -> Path:
    """Directory for custom wake-word models (e.g. a trained hey_jev.onnx)."""
    path = jev_data_dir() / "wakeword"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_model_factory(model_ref: str):
    """Load an openWakeWord model by name (downloaded on first use) or file path."""
    try:
        from openwakeword.model import Model
    except ImportError as exc:
        raise WakeWordUnavailable(
            "openwakeword is not installed — run: pip install openwakeword"
        ) from exc
    ref = model_ref.strip()
    if ref and Path(ref).expanduser().is_file():
        logger.info("Wake-word: loading custom model file %s", ref)
        return Model(wakeword_models=[str(Path(ref).expanduser())],
                     inference_framework="onnx")
    name = ref or DEFAULT_MODEL_NAME
    try:
        return Model(wakeword_models=[name], inference_framework="onnx")
    except Exception:  # noqa: BLE001 — first run: model not cached yet
        logger.info("Wake-word: downloading community model '%s'", name)
    try:
        from openwakeword.utils import download_models

        download_models(model_names=[name])
        return Model(wakeword_models=[name], inference_framework="onnx")
    except WakeWordUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise WakeWordUnavailable(
            f"Could not download or load wake-word model '{name}': {exc}"
        ) from exc


class _MicCapture:
    """Blocking 16 kHz mono int16 mic reader. Tries sounddevice, then pyaudio."""

    def __init__(self) -> None:
        self._kind: str | None = None
        self._stream: Any = None
        self._pa: Any = None
        self._open()

    def _open(self) -> None:
        try:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                blocksize=CHUNK_SAMPLES,
            )
            self._stream.start()
            self._kind = "sounddevice"
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("Wake-word: sounddevice unavailable: %s", exc)
        try:
            import pyaudio

            self._pa = pyaudio.PyAudio()
            self._stream = self._pa.open(
                format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                input=True, frames_per_buffer=CHUNK_SAMPLES,
            )
            self._kind = "pyaudio"
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("Wake-word: pyaudio unavailable: %s", exc)
        raise WakeWordUnavailable(
            "No microphone backend found — install sounddevice "
            "(pip install sounddevice; on Linux also libportaudio2)"
        )

    def read_chunk(self):
        import numpy as np

        if self._kind == "sounddevice":
            data, _overflow = self._stream.read(CHUNK_SAMPLES)
            return np.asarray(data, dtype=np.int16).reshape(-1)[:CHUNK_SAMPLES]
        raw = self._stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
        return np.frombuffer(raw, dtype=np.int16)

    def close(self) -> None:
        try:
            if self._stream is not None:
                if self._kind == "sounddevice":
                    self._stream.stop()
                self._stream.close()
        finally:
            if self._pa is not None:
                self._pa.terminate()


class WakeWordService:
    """Owns the wake-word listener thread and its on/off state.

    `capture_factory` / `model_factory` are injectable so tests can fake the
    mic and the keyword model — no audio hardware needed.
    """

    def __init__(
        self,
        config: WakeWordConfig | None = None,
        on_wake: Callable[[dict[str, Any]], None] | None = None,
        capture_factory: Callable[[], Any] | None = None,
        model_factory: Callable[[str], Any] | None = None,
        state_path: Path | None = None,
    ) -> None:
        self._config = config or WakeWordConfig.from_settings()
        self._on_wake = on_wake
        self._capture_factory = capture_factory or _MicCapture
        self._model_factory = model_factory or _default_model_factory
        self._state_path = state_path or (jev_data_dir() / STATE_FILE)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._paused = False
        self._cooldown_until = 0.0
        self._event: dict[str, Any] | None = None
        self._model: Any = None
        self._model_name: str = ""
        self._unavailable_reason: str | None = None

    # -- persistence -----------------------------------------------------

    def _load_state(self) -> None:
        try:
            if self._state_path.is_file():
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "enabled" in data:
                    self._config.enabled = bool(data["enabled"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wake-word: couldn't read state file: %s", exc)

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps({"enabled": self._config.enabled}), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wake-word: couldn't persist state: %s", exc)

    # -- lifecycle -------------------------------------------------------

    def startup(self) -> None:
        """Called from the app lifespan: restore the toggle, start if enabled."""
        self._load_state()
        if self._config.enabled:
            try:
                self.set_enabled(True)
            except WakeWordUnavailable as exc:
                self._unavailable_reason = str(exc)
                logger.warning("Wake-word: enabled but unavailable: %s", exc)

    def shutdown(self) -> None:
        self._stop_thread()

    @property
    def is_listening(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        """Flip the master toggle (persisted). Raises WakeWordUnavailable."""
        with self._lock:
            self._config.enabled = bool(enabled)
            self._save_state()
        if enabled:
            try:
                self._start_thread()  # raises WakeWordUnavailable on missing deps
            except WakeWordUnavailable as exc:
                with self._lock:
                    self._unavailable_reason = str(exc)
                raise
        else:
            self._stop_thread()
        logger.info("Wake-word %s", "enabled" if enabled else "disabled")
        return self.status()

    def pause(self) -> None:
        """Suspend scoring (e.g. while a Jev turn is running)."""
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        """Resume scoring after a pause."""
        with self._lock:
            self._paused = False
            self._cooldown_until = 0.0

    # -- events ----------------------------------------------------------

    def take_event(self) -> dict[str, Any] | None:
        """Return and clear the pending wake event (polled by Electron)."""
        with self._lock:
            event, self._event = self._event, None
            return event

    def status(self) -> dict[str, Any]:
        with self._lock:
            paused = self._paused
            cooling = time.monotonic() < self._cooldown_until
        return {
            "enabled": self._config.enabled,
            "listening": self.is_listening,
            "paused": paused or cooling,
            "model": self._model_name or self._config.model,
            "model_ready": self._model is not None,
            "threshold": self._config.threshold,
            "available": self._unavailable_reason is None,
            "unavailable_reason": self._unavailable_reason,
        }

    # -- internals -------------------------------------------------------

    def _start_thread(self) -> None:
        if self.is_listening:
            return
        try:
            self._model = self._model_factory(self._config.model)
        except WakeWordUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise WakeWordUnavailable(f"Could not load wake-word model: {exc}") from exc
        names = self._wake_names()
        self._model_name = names[0] if names else self._config.model
        self._stop.clear()
        self._paused = False
        self._thread = threading.Thread(
            target=self._run, name="jev-wakeword", daemon=True
        )
        self._thread.start()
        logger.info("Wake-word listener started (model=%s)", self._model_name)

    def _wake_names(self) -> list[str]:
        names: list[str] = []
        for attr in ("models", "model_names"):
            value = getattr(self._model, attr, None)
            if isinstance(value, dict):
                names.extend(str(k) for k in value)
            elif isinstance(value, (list, tuple)):
                names.extend(str(v) for v in value)
        return names

    def _stop_thread(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._model = None

    def _fire(self, name: str, score: float) -> None:
        """A wake phrase was heard: raise the event and go quiet for a while."""
        event = {
            "wake": True,
            "at": time.time(),
            "model": name,
            "score": round(float(score), 3),
        }
        with self._lock:
            self._event = event
            self._cooldown_until = time.monotonic() + self._config.cooldown_s
        logger.info("Wake-word detected (%s %.2f) — pausing for %ds",
                    name, score, self._config.cooldown_s)
        if self._on_wake is not None:
            try:
                self._on_wake(event)
            except Exception:  # noqa: BLE001
                logger.exception("Wake-word on_wake callback failed")

    def _score_chunk(self, chunk) -> bool:
        """Score one 80 ms frame. Returns True if it fired."""
        with self._lock:
            paused = self._paused
            cooling = time.monotonic() < self._cooldown_until
        if paused or cooling:
            return False
        try:
            scores = self._model.predict(chunk) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Wake-word predict failed: %s", exc)
            return False
        for name, score in scores.items():
            try:
                if float(score) >= self._config.threshold:
                    self._fire(str(name), float(score))
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _run(self) -> None:
        capture = None
        try:
            capture = self._capture_factory()
            while not self._stop.is_set():
                try:
                    chunk = capture.read_chunk()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Wake-word mic read failed: %s", exc)
                    time.sleep(0.2)
                    continue
                if chunk is None:
                    time.sleep(0.02)
                    continue
                self._score_chunk(chunk)
        except WakeWordUnavailable as exc:
            self._unavailable_reason = str(exc)
            logger.warning("Wake-word listener stopped: %s", exc)
        except Exception:  # noqa: BLE001
            logger.exception("Wake-word listener crashed")
        finally:
            if capture is not None:
                try:
                    capture.close()
                except Exception:  # noqa: BLE001
                    pass


_wakeword_service: WakeWordService | None = None


def get_wakeword_service() -> WakeWordService:
    """Process-wide singleton, wired into the app lifespan."""
    global _wakeword_service
    if _wakeword_service is None:
        _wakeword_service = WakeWordService()
    return _wakeword_service
