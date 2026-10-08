"""Tests for the Elsyia TTS voice picker.

Piper itself, the mic, and the network are all faked — no model downloads,
no audio hardware. What is exercised for real: voice resolution precedence,
installed/downloaded detection, select persistence, hot-swap wiring, and
that downloads only ever happen on explicit request.
"""

import json
from pathlib import Path

import pytest

import app.services.elsyia.voice_picker as vp
from app.services.elsyia.voice_picker import (
    JARVIS_DEFAULT_VOICE,
    VoiceNotAvailable,
    download_voice,
    installed_voices,
    is_valid_voice_id,
    list_voices,
    preview_wav,
    resolve_active_voice,
    select_voice,
)


class _FakeSettings:
    PIPER_MODELS_DIR = "models/piper"
    PIPER_VOICE = "en_US-lessac-medium"
    PIPER_SPEED = 1.0
    ELSYIA_TTS_VOICE = ""


class _FakeProvider:
    """Stand-in for PiperTTSProvider: records which voice it was built with."""

    built_with: list = []

    def __init__(self, voice, models_dir, speed=1.0):
        self.voice = voice
        self.models_dir = models_dir
        self.speed = speed
        _FakeProvider.built_with.append(voice)

    async def synthesize(self, text):
        yield f"wav:{self.voice}:{text}".encode()


@pytest.fixture
def models_dir(tmp_path):
    d = tmp_path / "piper"
    d.mkdir()
    return d


def _install(d: Path, voice_id: str) -> None:
    (d / f"{voice_id}.onnx").write_bytes(b"fake-model")
    (d / f"{voice_id}.onnx.json").write_text('{"fake": true}')


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    monkeypatch.setattr(vp, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(vp, "PiperTTSProvider", _FakeProvider)
    _FakeProvider.built_with.clear()


# --- id validation -----------------------------------------------------------

def test_valid_ids():
    assert is_valid_voice_id("en_GB-alan-medium")
    assert is_valid_voice_id("en_US-ryan-high")
    assert is_valid_voice_id("en_US-lessac-x_low")


def test_invalid_ids():
    assert not is_valid_voice_id("alan")
    assert not is_valid_voice_id("enGB-alan-medium")
    assert not is_valid_voice_id("en_GB-alan-ultra")
    assert not is_valid_voice_id("")


# --- installed detection -----------------------------------------------------

def test_installed_detection(models_dir):
    _install(models_dir, "en_GB-alan-medium")
    (models_dir / "orphan.onnx").write_bytes(b"no-config")  # incomplete pair
    found = installed_voices(models_dir)
    assert found == {"en_GB-alan-medium"}


# --- resolution precedence ---------------------------------------------------

def test_resolve_falls_back_to_jarvis_default(tmp_path, models_dir, monkeypatch):
    class S(_FakeSettings):
        PIPER_VOICE = ""
        ELSYIA_TTS_VOICE = ""
    monkeypatch.setattr(vp, "get_settings", lambda: S())
    assert resolve_active_voice(tmp_path / "voice.json", models_dir) == JARVIS_DEFAULT_VOICE


def test_resolve_prefers_env_over_default(tmp_path, models_dir, monkeypatch):
    class S(_FakeSettings):
        ELSYIA_TTS_VOICE = "en_US-ryan-medium"
    monkeypatch.setattr(vp, "get_settings", lambda: S())
    assert resolve_active_voice(tmp_path / "voice.json", models_dir) == "en_US-ryan-medium"


def test_resolve_prefers_persisted_over_env(tmp_path, models_dir, monkeypatch):
    class S(_FakeSettings):
        ELSYIA_TTS_VOICE = "en_US-ryan-medium"
    monkeypatch.setattr(vp, "get_settings", lambda: S())
    state = tmp_path / "voice.json"
    state.write_text(json.dumps({"voice": "en_GB-alan-medium"}))
    assert resolve_active_voice(state, models_dir) == "en_GB-alan-medium"


# --- listing -----------------------------------------------------------------

def test_list_marks_installed_and_active(tmp_path, models_dir):
    _install(models_dir, "en_GB-alan-medium")
    state = tmp_path / "voice.json"
    state.write_text(json.dumps({"voice": "en_GB-alan-medium"}))
    result = list_voices(state, models_dir)
    assert result["active"] == "en_GB-alan-medium"
    alan = next(v for v in result["voices"] if v["id"] == "en_GB-alan-medium")
    assert alan["installed"] is True and alan["active"] is True
    ryan = next(v for v in result["voices"] if v["id"] == "en_US-ryan-medium")
    assert ryan["installed"] is False and ryan["active"] is False


def test_list_never_downloads(tmp_path, models_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(vp, "urlopen", lambda *a, **k: calls.append(1) or _boom())
    list_voices(tmp_path / "voice.json", models_dir)
    select_candidates = [v for v in list_voices(tmp_path / "voice.json", models_dir)["voices"]]
    assert calls == [] and select_candidates  # listing is strictly read-only


def _boom():
    raise AssertionError("network must not be touched")


# --- select ------------------------------------------------------------------

def test_select_persists_and_returns(tmp_path, models_dir):
    _install(models_dir, "en_US-ryan-medium")
    state = tmp_path / "voice.json"
    assert select_voice("en_US-ryan-medium", state, models_dir) == "en_US-ryan-medium"
    assert json.loads(state.read_text())["voice"] == "en_US-ryan-medium"
    assert resolve_active_voice(state, models_dir) == "en_US-ryan-medium"


def test_select_rejects_bad_id(tmp_path, models_dir):
    with pytest.raises(VoiceNotAvailable):
        select_voice("not-a-voice", tmp_path / "voice.json", models_dir)


def test_select_requires_download_first(tmp_path, models_dir):
    with pytest.raises(VoiceNotAvailable, match="not downloaded"):
        select_voice("en_GB-alan-medium", tmp_path / "voice.json", models_dir)


# --- hot-swap ----------------------------------------------------------------

def test_hot_swap_replaces_cached_provider(monkeypatch):
    import app.services.voice.factory as factory

    captured = {}

    class _FactoryFake:
        def __init__(self, voice, models_dir, speed=1.0):
            captured["voice"] = voice

    monkeypatch.setattr(factory, "PiperTTSProvider", _FactoryFake)
    snapshot = dict(factory._tts_providers)
    try:
        provider = factory.set_tts_voice("en_US-ryan-medium")
        assert captured["voice"] == "en_US-ryan-medium"
        assert factory.get_tts_provider("piper") is provider
    finally:
        factory._tts_providers.clear()
        factory._tts_providers.update(snapshot)


# --- preview -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_uses_requested_voice_without_changing_active(tmp_path, models_dir):
    _install(models_dir, "en_US-lessac-medium")
    _install(models_dir, "en_US-ryan-medium")
    state = tmp_path / "voice.json"
    select_voice("en_US-lessac-medium", state, models_dir)

    wav = await preview_wav("en_US-ryan-medium", "Hello there.", models_dir)
    assert wav.startswith(b"wav:en_US-ryan-medium:")
    # Active voice untouched by the preview.
    assert resolve_active_voice(state, models_dir) == "en_US-lessac-medium"


@pytest.mark.asyncio
async def test_preview_rejects_unknown_voice(models_dir):
    with pytest.raises(VoiceNotAvailable):
        await preview_wav("en_GB-alan-medium", "Hi.", models_dir)


# --- download ----------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.headers = {"Content-Length": str(len(payload))}
        self._pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        if self._pos >= len(self._payload):
            return b""
        chunk = self._payload[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk


def test_download_writes_pair_with_progress(models_dir, monkeypatch):
    payload = b"x" * (3 * 1024 * 1024)
    monkeypatch.setattr(vp, "urlopen", lambda req, timeout=300: _FakeResponse(payload))
    progress = []
    vp.download_voice("en_GB-alan-medium", models_dir,
                       progress_cb=lambda d, t, f: progress.append((d, t, f)))
    assert (models_dir / "en_GB-alan-medium.onnx").exists()
    assert (models_dir / "en_GB-alan-medium.onnx.json").exists()
    assert progress, "progress callback must fire during download"
    assert progress[-1][0] == progress[-1][1] == len(payload)
    # Now installed — and a second download is refused.
    assert "en_GB-alan-medium" in installed_voices(models_dir)
    with pytest.raises(VoiceNotAvailable, match="already downloaded"):
        vp.download_voice("en_GB-alan-medium", models_dir)


def test_download_rejects_bad_id(models_dir):
    with pytest.raises(VoiceNotAvailable):
        download_voice("bogus", models_dir)


def test_download_failure_cleans_partial_file(models_dir, monkeypatch):
    def _failing(req, timeout=300):
        raise OSError("network down")
    monkeypatch.setattr(vp, "urlopen", _failing)
    with pytest.raises(Exception):
        download_voice("en_GB-alan-medium", models_dir)
    assert not (models_dir / "en_GB-alan-medium.onnx").exists()
