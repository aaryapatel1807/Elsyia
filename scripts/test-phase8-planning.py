"""Phase 8 local planning and dependency safety checks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["PLAN_ENABLED"] = "true"
        os.environ["PLAN_DB_PATH"] = str(Path(temporary_dir) / "plans.db")
        os.environ["PLAN_MAX_TASKS"] = "10"

        from app.services.planning import PlanError, PlanManager, PlanTask

        manager = PlanManager(Path(temporary_dir) / "direct.db")
        plan = manager.create(
            "Inspect a local project safely",
            [
                PlanTask(id="inspect", title="Inspect repository", action_class="analysis"),
                PlanTask(
                    id="summarize",
                    title="Summarize findings",
                    dependencies=["inspect"],
                    action_class="analysis",
                ),
                PlanTask(
                    id="external",
                    title="Ask before external action",
                    dependencies=["summarize"],
                    action_class="external_side_effect",
                    tool_name="open_windows_settings",
                ),
            ],
            assumptions=["The repository root is configured locally."],
            risks=["The project may contain unsupported files."],
            reasoning_summary="Inspect first, summarize second, and require confirmation before the external action.",
        )
        assert plan.status == "draft"
        assert plan.tasks[0].status == "ready"
        assert plan.tasks[1].status == "pending"

        try:
            manager.create(
                "Cycle",
                [
                    PlanTask(id="a", title="A", dependencies=["b"]),
                    PlanTask(id="b", title="B", dependencies=["a"]),
                ],
            )
        except PlanError as exc:
            assert "cycle" in str(exc).lower()
        else:
            raise AssertionError("cyclic plan was accepted")

        try:
            manager.create("Unsafe", [PlanTask(id="shell", title="Shell", action_class="disallowed")])
        except PlanError as exc:
            assert "disallowed" in str(exc).lower() or "high-impact" in str(exc).lower()
        else:
            raise AssertionError("disallowed plan task was accepted")

        approved = manager.approve(plan.id)
        assert approved.status == "approved"
        first = manager.prepare_next(plan.id)
        assert first["status"] == "prepared"
        refreshed = manager.get(plan.id)
        assert refreshed.tasks[0].status == "running"

        refreshed.tasks[0].status = "completed"
        manager._save(refreshed)
        next_step = manager.prepare_next(plan.id)
        assert next_step["status"] == "prepared"

        refreshed = manager.get(plan.id)
        refreshed.tasks[1].status = "completed"
        manager._save(refreshed)
        confirmation = manager.prepare_next(plan.id)
        assert confirmation["status"] == "confirmation_required"
        assert confirmation["next_task"]["status"] == "awaiting_confirmation"

        paused = manager.pause(plan.id)
        assert paused.status == "paused"
        revised = manager.revise(plan.id, reasoning_summary="The user requested a revised plan.")
        assert revised.status == "draft"
        assert revised.version == 2
        cancelled = manager.cancel(plan.id)
        assert cancelled.status == "cancelled"

        import httpx
        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/plan/create",
                json={
                    "goal": "API plan",
                    "tasks": [{"id": "one", "title": "Inspect", "action_class": "analysis"}],
                },
            )
            assert created.status_code == 200, created.text
            plan_id = created.json()["plan"]["id"]
            detail = await client.get(f"/api/v1/plan/{plan_id}")
            assert detail.status_code == 200, detail.text
            approve = await client.post(f"/api/v1/plan/{plan_id}/approve")
            assert approve.status_code == 200, approve.text
            prepare = await client.post(f"/api/v1/plan/{plan_id}/execute")
            assert prepare.status_code == 200, prepare.text

    print("phase 8 planning checks passed")


if __name__ == "__main__":
    asyncio.run(main())
