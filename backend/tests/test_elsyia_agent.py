"""Tests for Elsyia agent mode: planner, executor, threading, confirm pauses.

The Ollama planner and the tool registry are both faked — no network,
no live mailbox, no real side effects.
"""

import pytest

import app.services.elsyia.agent as agent_module
from app.services.elsyia.agent import (
    AgentRunner,
    looks_multi_intent,
    resolve_placeholders,
)
from app.services.tools.registry import ToolExecutionResult


class _FakeRegistry:
    """In-memory registry honouring the confirmation gate."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.fail_on: set[str] = set()
        self.confirm_required = {"create_calendar_event", "send_gmail"}

    def list(self):
        return [
            {"name": n, "description": f"Fake {n}.",
             "confirmation_required": n in self.confirm_required}
            for n in ("search_gmail", "read_gmail", "create_calendar_event",
                      "message_whatsapp", "get_current_time", "send_gmail")
        ]

    def get(self, name):
        return {"name": name} if name in {
            t["name"] for t in self.list()
        } else None

    async def execute(self, name, arguments=None, *, confirmed=False):
        arguments = arguments or {}
        self.calls.append((name, dict(arguments), confirmed))
        if name in self.confirm_required and not confirmed:
            return ToolExecutionResult(
                status="confirmation_required", tool_name=name,
                confirmation_required=True,
                confirmation_message=f"Confirm {name}?",
            )
        if name in self.fail_on:
            return ToolExecutionResult(
                status="failed", tool_name=name, error="boom")
        return ToolExecutionResult(
            status="completed", tool_name=name,
            result=self._result(name, arguments))

    @staticmethod
    def _result(name, arguments):
        if name == "search_gmail":
            return {"query": arguments.get("query"),
                    "results": [{"id": "msg-1", "subject": "Flight confirmation"}],
                    "count": 1}
        if name == "read_gmail":
            return {"id": "msg-1", "subject": "Flight UA123",
                    "body": "Departs 10:00",
                    "departure_iso": "2026-10-05T10:00:00+05:30"}
        if name == "create_calendar_event":
            return {"title": arguments.get("title"), "status": "created"}
        if name == "message_whatsapp":
            return {"to": arguments.get("to"), "opened": True}
        if name == "get_current_time":
            return {"time": "2026-10-03T09:30:00+05:30"}
        if name == "send_gmail":
            return {"to": arguments.get("to"), "sent": True}
        return {}


@pytest.fixture
def fake_registry(monkeypatch):
    fake = _FakeRegistry()
    monkeypatch.setattr(agent_module, "registry", fake)
    return fake


def _planner_factory(steps, called_flag=None):
    async def _fake(text, settings=None):
        if called_flag is not None:
            called_flag.append(text)
        return steps
    return _fake


@pytest.fixture
def runner():
    return AgentRunner()


# --- placeholder resolution ---

def test_resolve_whole_value_keeps_type():
    completed = {1: {"results": [{"id": "msg-1"}]}}
    assert resolve_placeholders("{{steps.1.results.0.id}}", completed) == "msg-1"
    assert resolve_placeholders("{{ steps.last.results.0.id }}", completed) == "msg-1"


def test_resolve_embedded_interpolation_and_missing():
    completed = {2: {"subject": "Flight UA123"}}
    out = resolve_placeholders("Flight: {{steps.2.subject}} ({{steps.9.nope}})", completed)
    assert out == "Flight: Flight UA123 ()"


def test_resolve_nested_structures():
    completed = {1: {"id": "abc"}}
    args = {"a": "{{steps.1.id}}", "b": ["x", {"c": "{{steps.last.id}}"}]}
    assert resolve_placeholders(args, completed) == {
        "a": "abc", "b": ["x", {"c": "abc"}]}


def test_looks_multi_intent():
    assert looks_multi_intent("do X and then do Y")
    assert looks_multi_intent("do X; do Y")
    assert looks_multi_intent("find my flight and add to calendar")
    assert looks_multi_intent("grab my flight info from Gmail, put it on my calendar")
    assert not looks_multi_intent("what time is it")
    assert not looks_multi_intent("remind me to buy milk and eggs in 10 minutes")
    assert not looks_multi_intent("   ")


async def test_routed_but_multi_intent_still_plans(
    runner, fake_registry, monkeypatch
):
    """'find my flight and add to calendar' matches the file-search regex,
    but the trailing verb phrase means two actions — the planner must win."""
    called: list[str] = []
    monkeypatch.setattr(
        agent_module, "plan_with_llm", _planner_factory(_CHAIN_STEPS, called))
    plan = await runner.run_text(
        "find my flight and add to calendar",
        confirmed={"create_calendar_event"},
    )
    assert called != []  # planner engaged despite the fast-path match
    assert len(plan.steps) == 3
    assert plan.status == "completed"


# --- full chains ---

_CHAIN_STEPS = [
    {"tool": "search_gmail",
     "args": {"query": "flight itinerary", "max_results": 3},
     "say": "Finding your flight email…"},
    {"tool": "read_gmail",
     "args": {"message_id": "{{steps.1.results.0.id}}"},
     "say": "Reading the flight details…"},
    {"tool": "create_calendar_event",
     "args": {"title": "Flight {{steps.2.subject}}",
              "start": "{{steps.2.departure_iso}}",
              "description": "{{steps.2.body}}"},
     "say": "Adding it to your calendar…"},
]


async def test_three_step_chain_threads_outputs(
    runner, fake_registry, monkeypatch
):
    monkeypatch.setattr(
        agent_module, "plan_with_llm", _planner_factory(_CHAIN_STEPS))
    events: list[dict] = []
    plan = await runner.run_text(
        "grab my flight info from Gmail and put it on my calendar",
        confirmed={"create_calendar_event"},
        event_sink=events.append,
    )
    assert plan.status == "completed"
    assert [s.status for s in plan.steps] == ["completed"] * 3
    # step 2 received the id threaded from step 1's search results
    assert fake_registry.calls[1] == (
        "read_gmail", {"message_id": "msg-1"}, False)
    # step 3 received fields threaded from step 2's read
    assert fake_registry.calls[2][1]["title"] == "Flight Flight UA123"
    assert fake_registry.calls[2][1]["start"] == "2026-10-05T10:00:00+05:30"
    assert "Done — 3 steps" in plan.reply
    types = [e["type"] for e in events]
    assert types[0] == "plan_created"
    assert "step_started" in types and "step_completed" in types
    assert types[-1] == "plan_completed"
    assert plan.timings_ms["total_ms"] >= 0


async def test_failure_at_step_two_stops_with_partial_report(
    runner, fake_registry, monkeypatch
):
    monkeypatch.setattr(
        agent_module, "plan_with_llm", _planner_factory(_CHAIN_STEPS))
    fake_registry.fail_on.add("read_gmail")
    plan = await runner.run_text("do the chain", confirmed={"create_calendar_event"})
    assert plan.status == "failed"
    assert [s.status for s in plan.steps] == ["completed", "failed", "skipped"]
    assert "1 of 3 steps" in plan.reply
    assert "got stuck" in plan.reply
    # step 3 never ran
    assert all(c[0] != "create_calendar_event" for c in fake_registry.calls)


async def test_destructive_step_pauses_for_confirmation(
    runner, fake_registry, monkeypatch
):
    monkeypatch.setattr(
        agent_module, "plan_with_llm", _planner_factory(_CHAIN_STEPS))
    plan = await runner.run_text("do the chain")  # nothing confirmed
    assert plan.status == "awaiting_confirmation"
    pending = [s for s in plan.steps if s.status == "awaiting_confirmation"]
    assert len(pending) == 1 and pending[0].tool == "create_calendar_event"
    assert "tap confirm" in plan.reply
    # resume with the approval: the plan continues, earlier steps are NOT rerun
    calls_before = len(fake_registry.calls)
    resumed = await runner.confirm_plan(
        plan.plan_id, {"create_calendar_event"})
    assert resumed is not None and resumed.status == "completed"
    assert len(fake_registry.calls) == calls_before + 1
    assert fake_registry.calls[-1][0] == "create_calendar_event"
    assert fake_registry.calls[-1][2] is True  # executed as confirmed


async def test_confirm_unknown_plan_returns_none(runner):
    assert await runner.confirm_plan("nope", {"x"}) is None


async def test_single_intent_takes_fast_path_without_planner(
    runner, fake_registry, monkeypatch
):
    called: list[str] = []
    monkeypatch.setattr(
        agent_module, "plan_with_llm", _planner_factory([], called))
    plan = await runner.run_text("what time is it")
    assert called == []  # planner never engaged
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "get_current_time"
    assert plan.steps[0].status == "completed"
    assert plan.status == "completed"
    assert "It's " in plan.reply


async def test_planner_garbage_means_no_plan(runner, fake_registry, monkeypatch):
    async def _garbage(text, settings=None):
        return []  # planner found nothing usable

    monkeypatch.setattr(agent_module, "plan_with_llm", _garbage)
    plan = await runner.run_text("do something ineffable")
    assert plan.status == "no_plan"
    assert plan.steps == []
    assert "couldn't break that down" in plan.reply


async def test_step_timeout_fails_the_plan(runner, fake_registry, monkeypatch):
    import asyncio as _asyncio
    from types import SimpleNamespace

    async def _slow(name, arguments=None, *, confirmed=False):
        await _asyncio.sleep(5)
        return ToolExecutionResult(status="completed", tool_name=name, result={})

    monkeypatch.setattr(fake_registry, "execute", _slow)
    monkeypatch.setattr(
        agent_module, "get_settings",
        lambda: SimpleNamespace(ELSYIA_AGENT_MAX_STEPS=5,
                               ELSYIA_AGENT_STEP_TIMEOUT_S=1,
                               DEFAULT_LLM_PROVIDER="ollama"))
    monkeypatch.setattr(
        agent_module, "plan_with_llm",
        _planner_factory([{"tool": "get_current_time", "args": {},
                           "say": "Checking…"}]))
    plan = await runner.run_text("what time is it, slowly")
    assert plan.status == "failed"
    assert "Timed out" in plan.steps[0].error


async def test_cancel_plan(runner, fake_registry, monkeypatch):
    monkeypatch.setattr(
        agent_module, "plan_with_llm", _planner_factory(_CHAIN_STEPS))
    plan = await runner.run_text("do the chain")
    assert plan.status == "awaiting_confirmation"
    assert runner.cancel_plan(plan.plan_id) is True
    assert plan.status == "cancelled"
    assert await runner.confirm_plan(plan.plan_id, {"create_calendar_event"}) is None
