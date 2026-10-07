"""Ambient information tools: weather and live system stats.

Both are read-only and need no API keys:
- weather comes from wttr.in (free JSON endpoint, no signup),
- system stats prefer psutil and degrade gracefully to stdlib-only
  disk reporting when psutil isn't installed.
"""

from __future__ import annotations

import shutil
from typing import Any

import httpx

from app.services.tools.base import Tool, ToolError

_WTTR_URL = "https://wttr.in/{location}?format=j1"
_WTTR_TIMEOUT_S = 10.0


class GetWeatherTool(Tool):
    """Current weather and today's forecast for a place (or IP location)."""

    name = "get_weather"
    description = (
        "Get the current weather and today's high/low for a location, "
        "e.g. location='Vadodara'. Omit location to use the caller's "
        "approximate IP location. Free wttr.in backend, no API key."
    )

    async def run(self, location: str = "") -> dict[str, Any]:
        place = (location or "").strip()
        url = _WTTR_URL.format(location=place if place else "")
        try:
            async with httpx.AsyncClient(timeout=_WTTR_TIMEOUT_S) as client:
                response = await client.get(url, headers={"User-Agent": "jev-assistant"})
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 — network/weather service issues
            raise ToolError(f"Couldn't reach the weather service: {exc}") from exc
        try:
            current = (data.get("current_condition") or [{}])[0]
            today = (data.get("weather") or [{}])[0]
            hourly = today.get("hourly") or []
            area = (data.get("nearest_area") or [{}])[0]
            area_name = ", ".join(
                part.get("value", "")
                for part in area.get("areaName", [])
                if part.get("value")
            )
            desc = ", ".join(
                part.get("value", "")
                for part in current.get("weatherDesc", [])
                if part.get("value")
            )
            temps = [int(h.get("tempC", 0)) for h in hourly if str(h.get("tempC", "")).lstrip("-").isdigit()]
            return {
                "location": area_name or place or "current location",
                "description": desc or "unknown",
                "temp_c": current.get("tempC"),
                "feels_like_c": current.get("FeelsLikeC"),
                "humidity_pct": current.get("humidity"),
                "wind_kph": current.get("windspeedKmph"),
                "high_c": today.get("maxtempC"),
                "low_c": today.get("mintempC"),
                "day_high_c": max(temps) if temps else today.get("maxtempC"),
                "sunrise": (today.get("astronomy") or [{}])[0].get("sunrise"),
                "sunset": (today.get("astronomy") or [{}])[0].get("sunset"),
            }
        except (AttributeError, IndexError, TypeError, ValueError) as exc:
            raise ToolError(f"Weather service returned an unexpected shape: {exc}") from exc


class GetSystemStatsTool(Tool):
    """Live CPU / memory / disk snapshot of the machine Jev runs on."""

    name = "get_system_stats"
    description = (
        "Get current CPU usage percent, memory usage and disk usage of "
        "the host machine. Read-only; useful for 'how is my computer doing'."
    )

    async def run(self) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        try:
            import psutil  # type: ignore

            stats["cpu_percent"] = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            stats["memory_percent"] = mem.percent
            stats["memory_used_gb"] = round(mem.used / 1e9, 1)
            stats["memory_total_gb"] = round(mem.total / 1e9, 1)
        except ImportError:
            stats["cpu_percent"] = None
            stats["memory_percent"] = None
            stats["note"] = "psutil not installed — CPU/memory unavailable"
        disk = shutil.disk_usage(".")
        stats["disk_percent"] = round(100 * disk.used / disk.total, 1)
        stats["disk_free_gb"] = round(disk.free / 1e9, 1)
        stats["disk_total_gb"] = round(disk.total / 1e9, 1)
        return stats
