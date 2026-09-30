"""Regression checks for the remaining Phase 5 Windows controls."""

from __future__ import annotations

import asyncio


async def main() -> None:
    from app.services.tools import registry
    from app.services.tools.base import ToolError
    from app.services.tools.desktop_controls import GetDisplayBrightnessTool, GetSystemVolumeTool
    from app.services.tools.intent import route_intent

    assert route_intent("volume status").tool_name == "get_system_volume", route_intent("volume status")
    assert route_intent("set volume to 42").arguments == {"volume_percent": 42}, route_intent("set volume to 42")
    assert route_intent("brightness status").tool_name == "get_display_brightness", route_intent("brightness status")
    assert route_intent("set brightness to 55").arguments == {"brightness_percent": 55}, route_intent("set brightness to 55")
    assert route_intent("mute").tool_name == "set_system_mute", route_intent("mute")
    assert route_intent("open display settings").arguments == {"page": "display"}, route_intent("open display settings")

    volume = await registry.execute("set_system_volume", {"volume_percent": 42}, confirmed=False)
    assert volume.status == "confirmation_required"
    invalid_volume = await registry.execute("set_system_volume", {"volume_percent": 101}, confirmed=True)
    assert invalid_volume.status == "failed"

    brightness = await registry.execute("set_display_brightness", {"brightness_percent": 55}, confirmed=False)
    assert brightness.status == "confirmation_required"
    invalid_brightness = await registry.execute(
        "set_display_brightness", {"brightness_percent": -1}, confirmed=True
    )
    assert invalid_brightness.status == "failed"

    settings = await registry.execute("open_windows_settings", {"page": "unknown"}, confirmed=True)
    assert settings.status == "failed"

    try:
        current_volume = await GetSystemVolumeTool().run()
        assert 0 <= current_volume["volume_percent"] <= 100
        assert isinstance(current_volume["muted"], bool)
    except ToolError as exc:
        assert "Core Audio" in str(exc) or "volume" in str(exc).lower()

    try:
        current_brightness = await GetDisplayBrightnessTool().run()
        assert 0 <= current_brightness["brightness_percent"] <= 100
    except ToolError as exc:
        assert "brightness" in str(exc).lower() or "display" in str(exc).lower()

    print("phase 5 control checks passed")


if __name__ == "__main__":
    asyncio.run(main())
