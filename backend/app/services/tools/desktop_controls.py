"""Windows volume, brightness, and allowlisted settings controls."""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
from typing import Any

from app.core import get_settings
from app.services.tools.base import Tool, ToolError
from app.services.tools.desktop_automation import _limiter, _require_windows


async def _audio_endpoint() -> Any:
    _require_windows()

    def load() -> Any:
        try:
            from pycaw.pycaw import AudioUtilities

            device = AudioUtilities.GetSpeakers()
            endpoint = getattr(device, "EndpointVolume", None)
            if endpoint is None:
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume

                endpoint = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return endpoint
        except Exception as exc:
            raise ToolError("Windows Core Audio is unavailable on this computer.") from exc

    return await asyncio.to_thread(load)


class GetSystemVolumeTool(Tool):
    name = "get_system_volume"
    description = "Read the current Windows master volume and mute state."

    async def run(self) -> dict[str, Any]:
        _limiter.check()
        endpoint = await _audio_endpoint()
        try:
            level = await asyncio.to_thread(endpoint.GetMasterVolumeLevelScalar)
            muted = await asyncio.to_thread(endpoint.GetMute)
        except Exception as exc:
            raise ToolError("Could not read the Windows master volume.") from exc
        return {"volume_percent": round(float(level) * 100), "muted": bool(muted)}


class SetSystemVolumeTool(Tool):
    name = "set_system_volume"
    description = "Set Windows master volume from 0 to 100 percent; requires confirmation."

    async def run(self, volume_percent: int) -> dict[str, Any]:
        _limiter.check()
        if not 0 <= volume_percent <= 100:
            raise ToolError("Volume must be between 0 and 100 percent.")
        endpoint = await _audio_endpoint()
        try:
            await asyncio.to_thread(endpoint.SetMasterVolumeLevelScalar, volume_percent / 100.0, None)
        except Exception as exc:
            raise ToolError("Could not change the Windows master volume.") from exc
        return {"volume_percent": volume_percent, "status": "updated"}


class SetSystemMuteTool(Tool):
    name = "set_system_mute"
    description = "Mute or unmute Windows master audio; requires confirmation."

    async def run(self, muted: bool) -> dict[str, Any]:
        _limiter.check()
        endpoint = await _audio_endpoint()
        try:
            await asyncio.to_thread(endpoint.SetMute, bool(muted), None)
        except Exception as exc:
            raise ToolError("Could not change the Windows mute state.") from exc
        return {"muted": bool(muted), "status": "updated"}


async def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    _require_windows()
    try:
        return await asyncio.to_thread(
            subprocess.run,
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=get_settings().DESKTOP_ACTION_TIMEOUT_SECONDS,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError("Windows control command timed out or was unavailable.") from exc


class GetDisplayBrightnessTool(Tool):
    name = "get_display_brightness"
    description = "Read the current internal-display brightness percentage."

    async def run(self) -> dict[str, Any]:
        _limiter.check()
        result = await _run_powershell(
            "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | "
            "Where-Object {$_.Active -eq $true} | Select-Object -First 1 -ExpandProperty CurrentBrightness)"
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise ToolError("Display brightness is not available through this Windows display driver.")
        try:
            value = int(result.stdout.strip().splitlines()[-1])
        except ValueError as exc:
            raise ToolError("Windows returned an invalid brightness value.") from exc
        return {"brightness_percent": max(0, min(100, value))}


class SetDisplayBrightnessTool(Tool):
    name = "set_display_brightness"
    description = "Set internal-display brightness from 0 to 100 percent; requires confirmation."

    async def run(self, brightness_percent: int) -> dict[str, Any]:
        _limiter.check()
        if not 0 <= brightness_percent <= 100:
            raise ToolError("Brightness must be between 0 and 100 percent.")
        result = await _run_powershell(
            "$monitor = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
            "Select-Object -First 1; if ($null -eq $monitor) { exit 2 }; "
            f"$monitor.WmiSetBrightness(1, {brightness_percent})"
        )
        if result.returncode != 0:
            raise ToolError("Display brightness is not controllable through this Windows display driver.")
        return {"brightness_percent": brightness_percent, "status": "updated"}


def _run_powercfg(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["powercfg.exe", *arguments],
            capture_output=True,
            text=True,
            timeout=get_settings().DESKTOP_ACTION_TIMEOUT_SECONDS,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError("Windows power-management command timed out or was unavailable.") from exc


_POWER_PLAN_ALIASES = {
    "balanced": "SCHEME_BALANCED",
    "power_saver": "SCHEME_MIN",
    "high_performance": "SCHEME_MAX",
}


class GetPowerPlanTool(Tool):
    name = "get_power_plan"
    description = "Read the active Windows power plan without changing system settings."

    async def run(self) -> dict[str, str]:
        _limiter.check()
        _require_windows()
        result = await asyncio.to_thread(_run_powercfg, ["/getactivescheme"])
        if result.returncode != 0 or not result.stdout.strip():
            raise ToolError("Windows did not return the active power plan.")
        return {"active_plan": result.stdout.strip()[:500]}


class SetPowerPlanTool(Tool):
    name = "set_power_plan"
    description = "Set one of three allowlisted Windows power plans; requires explicit opt-in and confirmation."

    async def run(self, plan: str) -> dict[str, str]:
        _limiter.check()
        _require_windows()
        if not get_settings().DESKTOP_SYSTEM_SETTINGS_ENABLED:
            raise ToolError("Direct Windows system-settings changes are disabled by configuration.")
        normalized = "_".join(plan.lower().strip().split())
        alias = _POWER_PLAN_ALIASES.get(normalized)
        if alias is None:
            raise ToolError("Power plan must be balanced, power_saver, or high_performance.")
        result = await asyncio.to_thread(_run_powercfg, ["/setactive", alias])
        if result.returncode != 0:
            raise ToolError("Windows could not activate the requested power plan.")
        return {"plan": normalized, "status": "updated"}


_ALLOWED_SETTINGS = {
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "network": "ms-settings:network",
    "bluetooth": "ms-settings:bluetooth",
    "privacy": "ms-settings:privacy",
    "windows update": "ms-settings:windowsupdate",
    "windows_update": "ms-settings:windowsupdate",
    "apps": "ms-settings:appsfeatures",
}


class OpenWindowsSettingsTool(Tool):
    name = "open_windows_settings"
    description = "Open an allowlisted Windows Settings page; requires confirmation."

    async def run(self, page: str) -> dict[str, str]:
        _limiter.check()
        _require_windows()
        normalized = " ".join(page.lower().strip().split())
        uri = _ALLOWED_SETTINGS.get(normalized)
        if uri is None:
            raise ToolError(f"Settings page is not on the allowlist: {page}")
        try:
            await asyncio.to_thread(os.startfile, uri)
        except OSError as exc:
            raise ToolError("Windows could not open that Settings page.") from exc
        return {"page": normalized, "status": "opened"}
