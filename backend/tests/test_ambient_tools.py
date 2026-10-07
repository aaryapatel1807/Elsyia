"""Tests for ambient tools (weather, system stats) and their intents."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tools.ambient_tools import GetSystemStatsTool, GetWeatherTool
from app.services.tools.base import ToolError
from app.services.tools.intent import route_intent


def _route(text):
    result = route_intent(text)
    assert result is not None, f"no intent routed for {text!r}"
    return result.tool_name, result.arguments


def test_weather_intents():
    name, args = _route("what's the weather")
    assert name == "get_weather" and args["location"] == ""
    name, args = _route("what is the weather in Mumbai")
    assert (name, args["location"]) == ("get_weather", "mumbai")
    name, args = _route("weather in delhi")
    assert (name, args["location"]) == ("get_weather", "delhi")
    name, _ = _route("do i need an umbrella")
    assert name == "get_weather"
    name, _ = _route("will it rain today")
    assert name == "get_weather"


def test_system_stats_intents():
    for text in ("system stats", "how is my computer doing", "cpu usage", "disk space"):
        name, _ = _route(text)
        assert name == "get_system_stats", text


_WTTR_FIXTURE = {
    "current_condition": [{
        "tempC": "31", "FeelsLikeC": "34", "humidity": "62",
        "windspeedKmph": "14",
        "weatherDesc": [{"value": "Partly cloudy"}],
    }],
    "weather": [{
        "maxtempC": "33", "mintempC": "24",
        "astronomy": [{"sunrise": "06:12 AM", "sunset": "06:38 PM"}],
        "hourly": [{"tempC": "31"}, {"tempC": "33"}, {"tempC": "29"}],
    }],
    "nearest_area": [{"areaName": [{"value": "Vadodara"}]}],
}


def _mock_wttr(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = response
    return client


@pytest.mark.asyncio
async def test_get_weather_parses_wttr():
    with patch(
        "app.services.tools.ambient_tools.httpx.AsyncClient",
        return_value=_mock_wttr(_WTTR_FIXTURE),
    ):
        result = await GetWeatherTool().run(location="Vadodara")
    assert result["location"] == "Vadodara"
    assert result["temp_c"] == "31"
    assert result["day_high_c"] == 33
    assert result["description"] == "Partly cloudy"


@pytest.mark.asyncio
async def test_get_weather_network_failure():
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.side_effect = OSError("no route")
    with patch(
        "app.services.tools.ambient_tools.httpx.AsyncClient", return_value=client
    ):
        with pytest.raises(ToolError):
            await GetWeatherTool().run(location="Nowhere")


@pytest.mark.asyncio
async def test_get_system_stats_without_psutil():
    with patch.dict("sys.modules", {"psutil": None}):
        # Force the guarded import to fail.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("no psutil")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = await GetSystemStatsTool().run()
    assert result["cpu_percent"] is None
    assert result["disk_percent"] >= 0
    assert result["disk_free_gb"] >= 0
