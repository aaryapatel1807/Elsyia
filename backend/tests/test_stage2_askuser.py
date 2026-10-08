"""Tests for Stage-2 LLM intent routing, ask_user mid-plan input, briefing."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core import get_settings
from app.services.tools.intent import (
    looks_like_command,
    route_intent,
    route_with_llm,
)


class _FakeLLM:
    def __init__(self, reply):
        self._reply = reply

    async def generate(self, messages, temperature=0.0, max_tokens=300):
        yield self._reply


_CATALOG = [
    {"name": "get_weather", "description": "Get weather"},
    {"name": "set_timer", "description": "Set a timer"},
]


def test_looks_like_command():
    assert looks_like_command("play some jazz")
    assert looks_like_command("dim the screen a little")
    assert not looks_like_command("what is the weather like")  # question -> chat LLM
    assert not looks_like_command("tell me a story about dragons in space someday")
    assert not looks_like_command("hi")
    assert not looks_like_command("")


@pytest.mark.asyncio
async def test_route_with_llm_valid_tool():
    llm = _FakeLLM(json.dumps({"tool": "get_weather", "args": {"location": "Goa"}}))
    result = await route_with_llm("how is the beach weather", llm, _CATALOG)
    assert result is not None
    assert result.tool_name == "get_weather"
    assert result.arguments == {"location": "Goa"}
    assert result.confidence == 0.80


@pytest.mark.asyncio
async def test_route_with_llm_rejects_unknown_tool():
    llm = _FakeLLM(json.dumps({"tool": "launch_nukes", "args": {}}))
    assert await route_with_llm("do something", llm, _CATALOG) is None


@pytest.mark.asyncio
async def test_route_with_llm_abstain():
    llm = _FakeLLM(json.dumps({"tool": None, "args": {}}))
    assert await route_with_llm("hmm", llm, _CATALOG) is None


@pytest.mark.asyncio
async def test_route_with_llm_garbage():
    llm = _FakeLLM("not json at all {{{")
    assert await route_with_llm("hmm", llm, _CATALOG) is None


def test_briefing_intent():
    for text in ("morning briefing", "brief me", "what does my day look like"):
        result = route_intent(text)
        assert result is not None and result.tool_name == "morning_briefing", text


@pytest.mark.asyncio
async def test_morning_briefing_composes():
    from app.services.tools.ambient_tools import MorningBriefingTool

    async def fake_weather(location=""):
        return {
            "location": "Vadodara", "description": "Sunny", "temp_c": "31",
            "day_high_c": 33, "low_c": "24",
        }

    with patch(
        "app.services.tools.ambient_tools.GetWeatherTool.run",
        side_effect=fake_weather,
    ), patch(
        "app.services.tools.reminders.ListRemindersTool.run",
        new=AsyncMock(return_value={"reminders": [{"title": "Call mom"}], "count": 1}),
    ), patch(
        "app.services.elsyia.calendar.CalendarTodayTool.run",
        new=AsyncMock(return_value={"events": [{"title": "Standup", "start": "10:00"}], "count": 1}),
    ):
        result = await MorningBriefingTool().run()
    assert "Standup" in result["summary"]
    assert "Call mom" in result["summary"]
    assert "Vadodara" in result["summary"]


@pytest.mark.asyncio
async def test_ask_user_pauses_and_resumes():
    from app.services.elsyia.agent import AgentRunner, AgentStep, AgentPlan

    runner = AgentRunner()
    plan = AgentPlan(plan_id="test123", message="test")
    plan.steps = [
        AgentStep(seq=1, tool="ask_user",
                  args={"question": "Which playlist?"}, say="Asking."),
        AgentStep(seq=2, tool="get_current_time", args={}, say="Checking time."),
    ]
    runner._plans["test123"] = plan
    events = []

    async def _emit(event):
        events.append(event)

    await runner._run_steps(plan, get_settings(), _emit)
    assert plan.status == "awaiting_input"
    assert plan.steps[0].status == "awaiting_input"
    assert "Which playlist?" in (plan.steps[0].confirmation_message or "")

    # Resume without an answer: still waiting.
    same = await runner.confirm_plan("test123", set())
    assert same is plan and plan.status == "awaiting_input"

    # Resume with an answer: step completes, plan continues to completion.
    resumed = await runner.confirm_plan(
        "test123", set(), user_input="lo-fi beats", event_sink=_emit
    )
    assert resumed is not None
    assert plan.steps[0].status == "completed"
    assert plan.steps[0].result == {"answer": "lo-fi beats"}
    assert plan.status == "completed"
    assert plan.steps[1].status == "completed"
