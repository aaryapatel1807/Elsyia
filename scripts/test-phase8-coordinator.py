"""Regression checks for bounded Phase 8 decomposition and coordination."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.planning.decomposer import decompose_goal  # noqa: E402
from app.services.planning.manager import PlanManager, PlanTask  # noqa: E402


class Phase8CoordinatorTests(unittest.TestCase):
    def test_decomposition_falls_back_without_local_model(self) -> None:
        with patch(
            "app.services.planning.decomposer.get_llm_provider",
            side_effect=RuntimeError("ollama unavailable"),
        ):
            tasks, reasoning = asyncio.run(decompose_goal("collect notes then summarize them"))
        self.assertGreaterEqual(len(tasks), 2)
        self.assertIn("fallback", reasoning.lower())
        self.assertEqual(tasks[0].action_class, "analysis")

    def test_parallel_preparation_and_bounded_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            manager = PlanManager(Path(temporary_dir) / "plans.db")
            plan = manager.create(
                "Analyze two local inputs",
                [
                    PlanTask("one", "Analyze input one", max_retries=1),
                    PlanTask("two", "Analyze input two"),
                    PlanTask("three", "Write external result", action_class="external_side_effect"),
                ],
            )
            manager.approve(plan.id)
            prepared = manager.prepare_parallel(plan.id)
            self.assertEqual(prepared["status"], "prepared_parallel")
            self.assertEqual({task["id"] for task in prepared["next_tasks"]}, {"one", "two"})
            retry = manager.record_task_result(plan.id, "one", success=False, error="temporary")
            self.assertEqual(retry["task"]["status"], "ready")
            self.assertEqual(retry["task"]["attempts"], 1)
            manager.prepare_parallel(plan.id)
            manager.record_task_result(plan.id, "one", success=False, error="permanent")
            self.assertEqual(manager.get(plan.id).tasks[0].status, "failed")

    def test_disabled_decomposition_fails_closed(self) -> None:
        get_settings().PLAN_DECOMPOSITION_ENABLED = False
        with self.assertRaises(Exception):
            asyncio.run(decompose_goal("do something"))
        get_settings().PLAN_DECOMPOSITION_ENABLED = True


if __name__ == "__main__":
    unittest.main(verbosity=2)
