"""Tests for the cross-platform reminder delivery chain."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tools.base import ToolError
from app.services.tools.reminders import deliver_reminder


@pytest.mark.asyncio
async def test_deliver_prefers_desktop_notifier():
    notifier = MagicMock()
    notifier.send = AsyncMock()
    with patch.dict("sys.modules", {"desktop_notifier": MagicMock()}):
        with patch(
            "desktop_notifier.DesktopNotifier", return_value=notifier
        ):
            await deliver_reminder({"title": "Take a break"})
    notifier.send.assert_awaited_once()
    kwargs = notifier.send.await_args.kwargs
    assert kwargs["message"] == "Take a break"


@pytest.mark.asyncio
async def test_deliver_falls_back_when_notifier_fails(monkeypatch):
    notifier = MagicMock()
    notifier.send = AsyncMock(side_effect=OSError("no daemon"))
    monkeypatch.setitem(__import__("sys").modules, "desktop_notifier", MagicMock())
    with patch("desktop_notifier.DesktopNotifier", return_value=notifier):
        # Linux VM: msg.exe path unavailable -> ToolError keeps it pending.
        with pytest.raises(ToolError):
            await deliver_reminder({"title": "Take a break"})


@pytest.mark.asyncio
async def test_deliver_without_package_on_linux():
    import sys

    # sys.modules entry of None makes `from desktop_notifier import ...`
    # raise ImportError — on this Linux VM that means ToolError.
    with patch.dict(sys.modules, {"desktop_notifier": None}):
        with pytest.raises(ToolError):
            await deliver_reminder({"title": "x"})
