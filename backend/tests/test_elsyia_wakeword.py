"""Tests for the Elsyia wake-word listener.

The microphone and the keyword model are faked — no audio hardware, no
model download, no network. The trigger wiring (detection -> wake event)
is exercised for real through the service's listener thread.
"""

import time

import numpy as np
import pytest

from app.services.elsyia.wakeword import (
    WakeWordConfig,
    WakeWordService,
    WakeWordUnavailable,
)

CHUNK = np.zeros(1280, dtype=np.int16)


class _FakeModel:
    def __init__(self, score=0.0):
        self.score = score
        self.models = {"hey_jarvis": None}
        self.calls = 0

    def predict(self, chunk):
        self.calls += 1
        assert len(chunk) == 1280
        return {"hey_jarvis": self.score}


class _FakeCapture:
    def __init__(self):
        self.closed = False

    def read_chunk(self):
        time.sleep(0.01)
        return CHUNK

    def close(self):
        self.closed = True


def _make_service(tmp_path, score=0.0, model_factory=None):
    fired: list = []
    config = WakeWordConfig(model="hey_jarvis", threshold=0.5, cooldown_s=60)
    if model_factory is None:
        model_factory = lambda ref: _FakeModel(score)  # noqa: E731
    svc = WakeWordService(
        config=config,
        on_wake=fired.append,
        capture_factory=_FakeCapture,
        model_factory=model_factory,
        state_path=tmp_path / "wakeword.json",
    )
    return svc, fired


def _wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_wake_event_fires_on_detection(tmp_path):
    svc, fired = _make_service(tmp_path, score=0.9)
    try:
        svc.set_enabled(True)
        assert _wait_for(lambda: svc.take_event() is not None)
        assert len(fired) == 1
        assert fired[0]["wake"] is True
        assert fired[0]["model"] == "hey_jarvis"
        assert fired[0]["score"] >= 0.5
    finally:
        svc.set_enabled(False)
    assert not svc.is_listening


def test_no_event_below_threshold_stays_asleep(tmp_path):
    svc, fired = _make_service(tmp_path, score=0.1)
    try:
        svc.set_enabled(True)
        assert svc.is_listening  # idling on the mic...
        time.sleep(0.4)
        assert svc.take_event() is None  # ...but nothing heard
        assert fired == []
        assert svc._model.calls > 0  # frames are actually being scored
    finally:
        svc.set_enabled(False)


def test_pause_suppresses_detection_until_resume(tmp_path):
    svc, fired = _make_service(tmp_path, score=0.9)
    try:
        svc.set_enabled(True)
        svc.pause()
        time.sleep(0.4)
        assert svc.take_event() is None
        assert fired == []
        svc.resume()
        assert _wait_for(lambda: svc.take_event() is not None)
        assert len(fired) == 1
    finally:
        svc.set_enabled(False)


def test_cooldown_after_wake(tmp_path):
    svc, fired = _make_service(tmp_path, score=0.9)
    svc._model = _FakeModel(score=0.9)  # no thread needed for scoring logic
    assert svc._score_chunk(CHUNK) is True
    assert svc.take_event() is not None
    # Still "hearing" the phrase, but the cooldown keeps it quiet.
    assert svc._score_chunk(CHUNK) is False
    assert svc.take_event() is None
    assert len(fired) == 1


def test_event_cleared_after_take(tmp_path):
    svc, _ = _make_service(tmp_path, score=0.9)
    svc._model = _FakeModel(score=0.9)
    svc._score_chunk(CHUNK)
    first = svc.take_event()
    assert first and first["wake"] is True
    assert svc.take_event() is None


def test_enable_fails_cleanly_without_dependencies(tmp_path):
    def _boom(ref):
        raise WakeWordUnavailable("openwakeword is not installed")

    svc, _ = _make_service(tmp_path, model_factory=_boom)
    with pytest.raises(WakeWordUnavailable):
        svc.set_enabled(True)
    status = svc.status()
    assert status["available"] is False
    assert "openwakeword" in status["unavailable_reason"]
    assert status["listening"] is False


def test_toggle_persists_across_restart(tmp_path):
    svc, _ = _make_service(tmp_path, score=0.0)
    svc.set_enabled(True)
    assert (tmp_path / "wakeword.json").is_file()

    svc2, _ = _make_service(tmp_path, score=0.0)
    try:
        # A fresh service restores the toggle from disk and starts listening.
        svc2.startup()
        assert svc2.is_listening
        assert svc2.status()["enabled"] is True
    finally:
        svc2.set_enabled(False)
        svc.set_enabled(False)


def test_status_shape(tmp_path):
    svc, _ = _make_service(tmp_path)
    status = svc.status()
    assert status == {
        "enabled": False,
        "listening": False,
        "paused": False,
        "model": "hey_jarvis",
        "model_ready": False,
        "threshold": 0.5,
        "available": True,
        "unavailable_reason": None,
    }
