"""Phase 9 autonomous-agent isolation and lifecycle checks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["AGENTS_ENABLED"] = "true"
        os.environ["AGENTS_WORKER_ENABLED"] = "false"
        os.environ["AGENTS_DB_PATH"] = str(Path(temporary_dir) / "agents.db")
        os.environ["AGENTS_MIN_INTERVAL_SECONDS"] = "300"
        os.environ["AGENTS_MAX_RUNTIME_SECONDS"] = "120"
        os.environ["AGENTS_MAX_TOOL_CALLS_PER_RUN"] = "3"
        os.environ["AGENTS_MAX_NOTIFICATIONS_PER_DAY"] = "2"

        from app.services.agents import AgentBudget, AgentError, AgentManager

        manager = AgentManager(Path(temporary_dir) / "direct.db")
        agent = manager.create(
            "Local inspector",
            "Inspect the local desktop safely",
            allowed_tools=["list_windows", "get_active_window"],
            interval_seconds=300,
            budget=AgentBudget(
                max_runs=2,
                max_runtime_seconds=60,
                max_tool_calls_per_run=2,
                max_notifications_per_day=1,
            ),
        )
        assert agent.status == "draft"
        assert agent.allowed_tools == ["list_windows", "get_active_window"]

        try:
            manager.create("Bad tool", "Should fail", allowed_tools=["unknown_tool"])
        except AgentError as exc:
            assert "unknown" in str(exc).lower() or "unavailable" in str(exc).lower()
        else:
            raise AssertionError("agent accepted an unavailable tool")

        started = manager.start(agent.id)
        assert started.status == "scheduled"
        assert started.next_run_at
        prepared = manager.prepare_run(agent.id)
        assert prepared["status"] == "prepared"
        assert prepared["agent"]["runs_used"] == 1
        assert prepared["confirmation_required"] is False

        running = manager.get(agent.id)
        assert running.status == "running"
        stopped = manager.stop(agent.id)
        assert stopped.status == "stopped"

        manager.start(agent.id)
        manager.prepare_run(agent.id)
        manager.stop(agent.id)
        manager.start(agent.id)
        exhausted = manager.prepare_run(agent.id, force=True)
        assert exhausted["status"] == "blocked"
        assert "budget" in exhausted["error"].lower()

        manager.clear_emergency_stop()
        manager.emergency_stop()
        assert manager.emergency_stop_status() is True
        try:
            manager.start(agent.id)
        except AgentError as exc:
            assert "emergency" in str(exc).lower()
        else:
            raise AssertionError("agent started while emergency stop was active")
        manager.clear_emergency_stop()
        assert manager.emergency_stop_status() is False

        events = manager.events(agent.id)
        assert events
        assert any(event["event_type"] == "created" for event in events)
        assert any(event["event_type"] == "run_prepared" for event in events)

        import httpx
        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/agents/create",
                json={
                    "name": "API inspector",
                    "purpose": "Inspect safely",
                    "allowed_tools": ["list_windows"],
                    "budget": {"max_runs": 1, "max_runtime_seconds": 60, "max_tool_calls_per_run": 1, "max_notifications_per_day": 2},
                },
            )
            assert created.status_code == 200, created.text
            agent_id = created.json()["agent"]["id"]
            listed = await client.get("/api/v1/agents")
            assert listed.status_code == 200, listed.text
            started_api = await client.post(f"/api/v1/agents/{agent_id}/start")
            assert started_api.status_code == 200, started_api.text
            run_api = await client.post(f"/api/v1/agents/{agent_id}/run", json={"force": True})
            assert run_api.status_code == 200, run_api.text
            assert run_api.json()["status"] == "prepared"
            stopped_api = await client.post(f"/api/v1/agents/{agent_id}/stop")
            assert stopped_api.status_code == 200, stopped_api.text

    print("phase 9 agent checks passed")


if __name__ == "__main__":
    asyncio.run(main())
