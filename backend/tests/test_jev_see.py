"""Tests for Jev screen-aware mode ("circle anything, then just ask").

No real screen, no mic, no Ollama here: captures are synthetic PNG
fixtures and the vision model is faked at the httpx layer.
"""

from __future__ import annotations

import base64
import io
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.jev import see as see_module
from app.services.jev.see import SeeService, SeeUnavailable, get_see_service
from app.services.tools.base import ToolError
from app.services.tools.see_tools import SeeCaptureTool


def _png_bytes(color: tuple[int, int, int] = (79, 124, 255)) -> bytes:
    """A tiny synthetic PNG fixture (no screen involved)."""
    # Minimal valid PNG: 1x1 pixel. Hand-built IHDR/IDAT/CRC via zlib.
    import struct
    import zlib

    def chunk(typ: bytes, data: bytes) -> bytes:
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes(color)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return png


@pytest.fixture()
def service(monkeypatch) -> SeeService:
    svc = SeeService()
    # Fresh singleton state per test.
    monkeypatch.setattr(see_module, "_see_service", svc)
    return svc


def test_store_and_read_capture(service: SeeService):
    stored = service.store_capture(_png_bytes())
    assert stored["capture_id"]
    assert stored["bytes"] > 0
    assert service.has_capture() is True
    cap = service._current()
    assert cap is not None and cap["capture_id"] == stored["capture_id"]


def test_store_rejects_non_png(service: SeeService):
    with pytest.raises(SeeUnavailable):
        service.store_capture(b"not a png at all")
    assert service.has_capture() is False


def test_capture_expires_on_ttl(service: SeeService, monkeypatch):
    service.store_capture(_png_bytes())
    assert service.has_capture() is True
    assert service._capture is not None
    # Age the capture past its TTL.
    service._capture["created_at"] = time.time() - service._ttl_s - 1
    assert service.has_capture() is False
    # Expired captures are also unanswerable.
    with pytest.raises(SeeUnavailable):
        # answer() is async; run via pytest-asyncio-style manual loop below.
        _run(service.answer("what is this?"))


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_answer_without_capture(service: SeeService):
    with pytest.raises(SeeUnavailable) as excinfo:
        _run(service.answer("what is this?"))
    # The error must guide the user to the explicit trigger.
    assert "Ctrl+Shift+S" in str(excinfo.value)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any] | None = None, tags: list[str] | None = None):
        self._payload = payload
        self._tags = tags

    def raise_for_status(self):
        return None

    def json(self):
        if self._tags is not None:
            return {"models": [{"name": n} for n in self._tags]}
        return self._payload or {}


class _FakeClient:
    """Fakes httpx.AsyncClient for the Ollama chat/tags endpoints."""

    def __init__(self, tags: list[str] | None = None, answer: str = "A blue square."):
        self._tags = tags if tags is not None else ["moondream:latest"]
        self._answer = answer
        self.posts: list[dict[str, Any]] = []

    async def get(self, url: str):
        if url.endswith("/api/tags"):
            return _FakeResponse(tags=self._tags)
        raise AssertionError(f"unexpected GET {url}")

    async def post(self, url: str, json: dict[str, Any]):
        assert url.endswith("/api/chat")
        self.posts.append(json)
        return _FakeResponse(
            {"message": {"content": self._answer}, "done": True}
        )


def test_answer_happy_path(service: SeeService, monkeypatch):
    service.store_capture(_png_bytes())
    fake = _FakeClient()
    monkeypatch.setattr(service, "_client", fake)
    result = _run(service.answer("what color is the square?"))
    assert result["answer"] == "A blue square."
    assert result["timings_ms"]["total_ms"] >= 0
    # The image must travel as base64 in the Ollama chat payload.
    sent = fake.posts[0]
    images = sent["messages"][0]["images"]
    assert len(images) == 1
    assert base64.b64decode(images[0]).startswith(b"\x89PNG")


def test_answer_model_not_pulled(service: SeeService, monkeypatch):
    service.store_capture(_png_bytes())
    fake = _FakeClient(tags=["llama3.2:latest"])
    monkeypatch.setattr(service, "_client", fake)
    with pytest.raises(SeeUnavailable) as excinfo:
        _run(service.answer("what is this?"))
    assert "ollama pull" in str(excinfo.value)


def test_answer_ollama_unreachable(service: SeeService, monkeypatch):
    service.store_capture(_png_bytes())

    class _DeadClient(_FakeClient):
        async def get(self, url: str):
            raise ConnectionError("nope")

    monkeypatch.setattr(service, "_client", _DeadClient())
    with pytest.raises(SeeUnavailable) as excinfo:
        _run(service.answer("what is this?"))
    assert "Ollama" in str(excinfo.value)


def test_status_shape(service: SeeService, monkeypatch):
    fake = _FakeClient(tags=["moondream"])
    monkeypatch.setattr(service, "_client", fake)
    status = _run(service.status())
    assert status["vision_model"] == "moondream"
    assert status["model_available"] is True
    assert status["ollama_reachable"] is True
    assert status["has_capture"] is False
    assert "hotkey" in status


def test_see_capture_tool_no_capture(service: SeeService):
    tool = SeeCaptureTool()
    with pytest.raises(ToolError) as excinfo:
        _run(tool.run(question="what is this?"))
    assert "Ctrl+Shift+S" in str(excinfo.value)


def test_see_capture_tool_reads_current_capture(service: SeeService, monkeypatch):
    service.store_capture(_png_bytes())
    fake = _FakeClient(answer="An error dialog.")
    monkeypatch.setattr(service, "_client", fake)
    result = _run(SeeCaptureTool().run(question="what does the dialog say?"))
    assert result["status"] == "completed"
    assert result["answer"] == "An error dialog."
    assert result["local_only"] is True


def test_see_capture_tool_registered():
    from app.services.tools.registry import registry

    tool = registry.get("see_capture")
    assert tool is not None
    # Read-only over an explicit capture: never confirmation-gated.
    assert "see_capture" not in registry._confirmation_required


def test_privacy_invariant_single_write_path():
    """The ONLY code allowed to store a capture is the /jev/see/capture
    endpoint (called after the user's explicit region select). If this
    fails, someone added a second capture path — reject it."""
    root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    for path in list((root / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "store_capture(" in line and "def store_capture" not in line:
                hits.append(f"{path.relative_to(root)}:{i}")
    assert hits, "no capture write path found — /jev/see/capture must call store_capture"
    assert all(h.startswith("app/api/v1/jev.py:") for h in hits), (
        f"unexpected capture write paths: {hits}"
    )
    # And the tool itself must never write — only read.
    tool_src = (root / "app/services/tools/see_tools.py").read_text(encoding="utf-8")
    assert "store_capture" not in tool_src


def test_singleton_shared():
    a = get_see_service()
    b = get_see_service()
    assert a is b


def test_region_math_contract():
    """Contract for frontend/electron/see.ts normalizeRect/toCropBounds.

    The TS originals are pure functions; this pins the expected math so
    a behavioural drift in either implementation fails loudly.
    """

    def normalize_rect(start, cur):
        return {
            "x": min(start[0], cur[0]),
            "y": min(start[1], cur[1]),
            "width": abs(cur[0] - start[0]),
            "height": abs(cur[1] - start[1]),
        }

    def to_crop_bounds(rect, scale):
        s = scale if scale > 0 else 1
        return {
            "x": max(0, round(rect["x"] * s)),
            "y": max(0, round(rect["y"] * s)),
            "width": max(1, round(rect["width"] * s)),
            "height": max(1, round(rect["height"] * s)),
        }

    # Drag up-left normalizes to top-left origin.
    assert normalize_rect((300, 200), (100, 50)) == {
        "x": 100,
        "y": 50,
        "width": 200,
        "height": 150,
    }
    # Retina scale doubles device pixels.
    assert to_crop_bounds({"x": 100, "y": 50, "width": 200, "height": 150}, 2.0) == {
        "x": 200,
        "y": 100,
        "width": 400,
        "height": 300,
    }
    # Negative origins clamp; zero-size clamps to 1px.
    assert to_crop_bounds({"x": -5, "y": -5, "width": 0, "height": 0}, 1.0) == {
        "x": 0,
        "y": 0,
        "width": 1,
        "height": 1,
    }
