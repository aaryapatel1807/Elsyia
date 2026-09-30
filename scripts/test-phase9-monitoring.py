"""Regression checks for local monitor triggers and notification policy."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.agents.manager import AgentBudget, AgentManager  # noqa: E402
from app.services.agents.monitoring import MonitorError, MonitorManager  # noqa: E402


class Phase9MonitoringTests(unittest.TestCase):
    def test_file_monitor_is_safe_deduplicated_and_budgeted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            db = root / "agents.db"
            watched = root / "watched.txt"
            watched.write_text("one", encoding="utf-8")
            agents = AgentManager(db)
            agent = agents.create(
                "Monitor",
                "Watch one local file",
                allowed_roots=[str(root)],
                budget=AgentBudget(max_notifications_per_day=1),
            )
            monitors = MonitorManager(db, agents)
            monitors.create(agent.id, "file", {"path": str(watched)})
            self.assertEqual(monitors.evaluate(), [])
            watched.write_text("two", encoding="utf-8")
            first = monitors.evaluate()
            self.assertEqual(len(first), 1)
            watched.write_text("three", encoding="utf-8")
            self.assertEqual(monitors.evaluate(), [])
            self.assertEqual(len(monitors.notifications.list()), 1)
            with self.assertRaises(MonitorError):
                monitors.create(agent.id, "file", {"path": str(root.parent / "outside.txt")})

    def test_metric_monitor_requires_allowlisted_metric_and_operator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            agents = AgentManager(root / "agents.db")
            agent = agents.create("Metric", "Watch local run count")
            monitors = MonitorManager(root / "agents.db", agents)
            monitors.create(agent.id, "metric", {"metric": "runs_used", "operator": "gte", "threshold": 2})
            self.assertEqual(monitors.evaluate({"runs_used": 1}), [])
            self.assertEqual(len(monitors.evaluate({"runs_used": 2})), 1)
            with self.assertRaises(MonitorError):
                monitors.create(agent.id, "metric", {"metric": "passwords", "operator": "eq", "threshold": 1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
