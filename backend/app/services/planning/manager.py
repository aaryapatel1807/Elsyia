"""Local Phase 8 plan persistence and dependency graph manager."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.core import get_settings


class PlanError(Exception):
    """Expected plan validation or persistence error."""


PLAN_STATUSES = {"draft", "approved", "running", "paused", "completed", "failed", "cancelled", "revised"}
TASK_STATUSES = {"pending", "ready", "awaiting_confirmation", "running", "completed", "failed", "blocked", "cancelled", "skipped"}
ACTION_CLASSES = {"analysis", "local_reversible", "external_side_effect", "high_impact", "disallowed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    configured = Path(get_settings().PLAN_DB_PATH)
    if configured.is_absolute():
        path = configured
    else:
        path = Path(__file__).parents[4] / configured
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _bounded(value: str | None, maximum: int, field_name: str) -> str:
    text = " ".join((value or "").strip().split())
    if len(text) > maximum:
        raise PlanError(f"{field_name} exceeds the configured length limit.")
    return text


@dataclass
class PlanTask:
    id: str
    title: str
    description: str = ""
    dependencies: list[str] = field(default_factory=list)
    action_class: str = "analysis"
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    max_retries: int = 0
    attempts: int = 0
    output: Any = None
    error: str | None = None
    reasoning_summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    id: str
    goal: str
    tasks: list[PlanTask]
    status: str = "draft"
    version: int = 1
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tasks"] = [task.as_dict() for task in self.tasks]
        return payload


class PlanManager:
    """SQLite-backed plan store with graph validation and lifecycle controls."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    assumptions_json TEXT NOT NULL,
                    risks_json TEXT NOT NULL,
                    reasoning_summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS plan_tasks (
                    plan_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    dependencies_json TEXT NOT NULL,
                    action_class TEXT NOT NULL,
                    tool_name TEXT,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    max_retries INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    output_json TEXT,
                    error TEXT,
                    reasoning_summary TEXT NOT NULL,
                    PRIMARY KEY (plan_id, task_id),
                    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS plan_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id TEXT NOT NULL,
                    task_id TEXT,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.commit()

    def validate_tasks(self, tasks: Iterable[PlanTask]) -> list[PlanTask]:
        normalized = list(tasks)
        if not normalized:
            raise PlanError("A plan must contain at least one task.")
        if len(normalized) > get_settings().PLAN_MAX_TASKS:
            raise PlanError("Plan exceeds the maximum task count.")
        identifiers = [task.id.strip() for task in normalized]
        if len(set(identifiers)) != len(identifiers) or any(not item for item in identifiers):
            raise PlanError("Task IDs must be non-empty and unique.")
        known = set(identifiers)
        graph: dict[str, list[str]] = {}
        for task in normalized:
            task.id = task.id.strip()
            task.title = _bounded(task.title, get_settings().PLAN_MAX_TEXT_CHARS, "Task title")
            task.description = _bounded(task.description, get_settings().PLAN_MAX_TEXT_CHARS, "Task description")
            task.reasoning_summary = _bounded(task.reasoning_summary, get_settings().PLAN_MAX_TEXT_CHARS, "Task reasoning")
            if not task.title:
                raise PlanError("Every task must have a title.")
            if task.action_class not in ACTION_CLASSES:
                raise PlanError(f"Unsupported task action class: {task.action_class}")
            if task.action_class in {"high_impact", "disallowed"}:
                raise PlanError("High-impact and disallowed actions cannot be created in the Phase 8 foundation.")
            if task.tool_name and len(task.tool_name) > 120:
                raise PlanError("Task tool name is too long.")
            if task.max_retries < 0 or task.max_retries > get_settings().PLAN_MAX_RETRIES:
                raise PlanError("Task retry count exceeds the configured limit.")
            task.dependencies = list(dict.fromkeys(task.dependencies))
            unknown = set(task.dependencies) - known
            if unknown:
                raise PlanError(f"Task {task.id} has unknown dependencies: {sorted(unknown)}")
            if task.id in task.dependencies:
                raise PlanError(f"Task {task.id} cannot depend on itself.")
            graph[task.id] = task.dependencies
        self._assert_acyclic(graph)
        return normalized

    @staticmethod
    def _assert_acyclic(graph: dict[str, list[str]]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise PlanError("Plan dependencies contain a cycle.")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    def create(
        self,
        goal: str,
        tasks: Iterable[PlanTask],
        *,
        assumptions: list[str] | None = None,
        risks: list[str] | None = None,
        reasoning_summary: str = "",
    ) -> Plan:
        if not get_settings().PLAN_ENABLED:
            raise PlanError("Planning is disabled.")
        normalized_goal = _bounded(goal, get_settings().PLAN_MAX_GOAL_CHARS, "Plan goal")
        if not normalized_goal:
            raise PlanError("Plan goal is required.")
        normalized_tasks = self.validate_tasks(tasks)
        now = _now()
        plan = Plan(
            id=uuid.uuid4().hex,
            goal=normalized_goal,
            tasks=normalized_tasks,
            assumptions=[_bounded(item, get_settings().PLAN_MAX_TEXT_CHARS, "Assumption") for item in (assumptions or [])],
            risks=[_bounded(item, get_settings().PLAN_MAX_TEXT_CHARS, "Risk") for item in (risks or [])],
            reasoning_summary=_bounded(reasoning_summary, get_settings().PLAN_MAX_TEXT_CHARS, "Plan reasoning"),
            created_at=now,
            updated_at=now,
        )
        self._refresh_ready_tasks(plan)
        self._save(plan)
        self._event(plan.id, None, "created", {"task_count": len(plan.tasks), "version": plan.version})
        return plan

    def _refresh_ready_tasks(self, plan: Plan) -> None:
        completed = {task.id for task in plan.tasks if task.status == "completed"}
        for task in plan.tasks:
            if task.status == "pending" and all(dependency in completed for dependency in task.dependencies):
                task.status = "ready"

    def _save(self, plan: Plan) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO plans
                (id, goal, status, version, assumptions_json, risks_json, reasoning_summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    plan.id,
                    plan.goal,
                    plan.status,
                    plan.version,
                    json.dumps(plan.assumptions),
                    json.dumps(plan.risks),
                    plan.reasoning_summary,
                    plan.created_at,
                    plan.updated_at,
                ),
            )
            connection.execute("DELETE FROM plan_tasks WHERE plan_id = ?", (plan.id,))
            for task in plan.tasks:
                connection.execute(
                    """INSERT INTO plan_tasks
                    (plan_id, task_id, title, description, dependencies_json, action_class, tool_name,
                     arguments_json, status, max_retries, attempts, output_json, error, reasoning_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        plan.id,
                        task.id,
                        task.title,
                        task.description,
                        json.dumps(task.dependencies),
                        task.action_class,
                        task.tool_name,
                        json.dumps(task.arguments),
                        task.status,
                        task.max_retries,
                        task.attempts,
                        json.dumps(task.output) if task.output is not None else None,
                        task.error,
                        task.reasoning_summary,
                    ),
                )
            connection.commit()

    def _event(self, plan_id: str, task_id: str | None, event_type: str, details: dict[str, Any]) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO plan_events (plan_id, task_id, event_type, details_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan_id, task_id, event_type, json.dumps(details)[:5000], _now()),
            )
            connection.commit()

    def get(self, plan_id: str) -> Plan:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            if row is None:
                raise PlanError("Plan was not found.")
            task_rows = connection.execute("SELECT * FROM plan_tasks WHERE plan_id = ? ORDER BY rowid", (plan_id,)).fetchall()
        tasks = [
            PlanTask(
                id=task["task_id"],
                title=task["title"],
                description=task["description"],
                dependencies=json.loads(task["dependencies_json"]),
                action_class=task["action_class"],
                tool_name=task["tool_name"],
                arguments=json.loads(task["arguments_json"]),
                status=task["status"],
                max_retries=task["max_retries"],
                attempts=task["attempts"],
                output=json.loads(task["output_json"]) if task["output_json"] else None,
                error=task["error"],
                reasoning_summary=task["reasoning_summary"],
            )
            for task in task_rows
        ]
        return Plan(
            id=row["id"],
            goal=row["goal"],
            tasks=tasks,
            status=row["status"],
            version=row["version"],
            assumptions=json.loads(row["assumptions_json"]),
            risks=json.loads(row["risks_json"]),
            reasoning_summary=row["reasoning_summary"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_plans(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id, goal, status, version, created_at, updated_at FROM plans ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_events(self, plan_id: str) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT task_id, event_type, details_json, created_at FROM plan_events WHERE plan_id = ? ORDER BY id",
                (plan_id,),
            ).fetchall()
        return [
            {
                "task_id": row["task_id"],
                "event_type": row["event_type"],
                "details": json.loads(row["details_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def approve(self, plan_id: str) -> Plan:
        plan = self.get(plan_id)
        if plan.status != "draft":
            raise PlanError("Only draft plans can be approved.")
        plan.status = "approved"
        plan.updated_at = _now()
        self._save(plan)
        self._event(plan.id, None, "approved", {"version": plan.version})
        return plan

    def pause(self, plan_id: str) -> Plan:
        plan = self.get(plan_id)
        if plan.status not in {"approved", "running"}:
            raise PlanError("Only approved or running plans can be paused.")
        plan.status = "paused"
        plan.updated_at = _now()
        self._save(plan)
        self._event(plan.id, None, "paused", {})
        return plan

    def cancel(self, plan_id: str) -> Plan:
        plan = self.get(plan_id)
        if plan.status in {"completed", "cancelled"}:
            raise PlanError("Plan is already terminal.")
        plan.status = "cancelled"
        for task in plan.tasks:
            if task.status not in {"completed", "failed", "cancelled", "skipped"}:
                task.status = "cancelled"
        plan.updated_at = _now()
        self._save(plan)
        self._event(plan.id, None, "cancelled", {})
        return plan

    def prepare_next(self, plan_id: str) -> dict[str, Any]:
        plan = self.get(plan_id)
        if plan.status not in {"approved", "running"}:
            raise PlanError("Plan must be approved before execution preparation.")
        self._refresh_ready_tasks(plan)
        ready = next((task for task in plan.tasks if task.status == "ready"), None)
        if ready is None:
            if all(task.status in {"completed", "skipped"} for task in plan.tasks):
                plan.status = "completed"
                plan.updated_at = _now()
                self._save(plan)
                self._event(plan.id, None, "completed", {})
                return {"plan": plan.as_dict(), "next_task": None, "status": "completed"}
            if any(task.status in {"failed", "blocked"} for task in plan.tasks):
                plan.status = "failed"
                plan.updated_at = _now()
                self._save(plan)
                return {"plan": plan.as_dict(), "next_task": None, "status": "blocked"}
            return {"plan": plan.as_dict(), "next_task": None, "status": "waiting"}
        plan.status = "running"
        if ready.action_class == "external_side_effect":
            ready.status = "awaiting_confirmation"
            plan.updated_at = _now()
            self._save(plan)
            self._event(plan.id, ready.id, "confirmation_required", {"tool_name": ready.tool_name})
            return {"plan": plan.as_dict(), "next_task": ready.as_dict(), "status": "confirmation_required"}
        ready.status = "running"
        plan.updated_at = _now()
        self._save(plan)
        self._event(plan.id, ready.id, "prepared", {"tool_name": ready.tool_name})
        return {"plan": plan.as_dict(), "next_task": ready.as_dict(), "status": "prepared"}

    def prepare_parallel(self, plan_id: str) -> dict[str, Any]:
        """Prepare independent analysis/local tasks together; side effects remain gated."""
        plan = self.get(plan_id)
        if plan.status not in {"approved", "running"}:
            raise PlanError("Plan must be approved before execution preparation.")
        self._refresh_ready_tasks(plan)
        ready = [
            task
            for task in plan.tasks
            if task.status == "ready" and task.action_class in {"analysis", "local_reversible"}
        ][: get_settings().PLAN_MAX_PARALLEL_TASKS]
        if not ready:
            return self.prepare_next(plan_id)
        plan.status = "running"
        for task in ready:
            task.status = "running"
            self._event(plan.id, task.id, "prepared_parallel", {"action_class": task.action_class})
        plan.updated_at = _now()
        self._save(plan)
        return {
            "plan": plan.as_dict(),
            "next_tasks": [task.as_dict() for task in ready],
            "status": "prepared_parallel",
        }

    def record_task_result(
        self,
        plan_id: str,
        task_id: str,
        *,
        success: bool,
        output: Any = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Record a bounded task result and schedule retry or terminal failure."""
        plan = self.get(plan_id)
        if plan.status not in {"running", "approved"}:
            raise PlanError("Plan is not accepting task results.")
        task = next((item for item in plan.tasks if item.id == task_id), None)
        if task is None:
            raise PlanError("Task was not found.")
        if task.status not in {"running", "awaiting_confirmation"}:
            raise PlanError("Task is not currently executing.")
        if output is not None:
            try:
                encoded_output = json.dumps(output, default=str)
            except (TypeError, ValueError) as exc:
                raise PlanError("Task output must be JSON-serializable.") from exc
            if len(encoded_output) > get_settings().PLAN_MAX_TEXT_CHARS * 4:
                raise PlanError("Task output exceeds the configured length limit.")
        task.output = output
        if success:
            task.status = "completed"
            task.error = None
            self._event(plan.id, task.id, "task_completed", {})
        else:
            task.attempts += 1
            task.error = _bounded(error, get_settings().PLAN_MAX_TEXT_CHARS, "Task error")
            if task.attempts <= task.max_retries:
                task.status = "ready"
                self._event(plan.id, task.id, "retry_scheduled", {"attempt": task.attempts})
            else:
                task.status = "failed"
                self._event(plan.id, task.id, "task_failed", {"attempts": task.attempts})
        self._refresh_ready_tasks(plan)
        if all(item.status in {"completed", "skipped"} for item in plan.tasks):
            plan.status = "completed"
        elif any(item.status == "failed" for item in plan.tasks):
            plan.status = "failed"
        else:
            plan.status = "running"
        plan.updated_at = _now()
        self._save(plan)
        return {"plan": plan.as_dict(), "task": task.as_dict(), "status": task.status}

    def revise(self, plan_id: str, goal: str | None = None, reasoning_summary: str | None = None) -> Plan:
        current = self.get(plan_id)
        if current.status == "running":
            raise PlanError("Running plans must be paused before revision.")
        current.status = "revised"
        current.version += 1
        if goal is not None:
            current.goal = _bounded(goal, get_settings().PLAN_MAX_GOAL_CHARS, "Plan goal")
        if reasoning_summary is not None:
            current.reasoning_summary = _bounded(reasoning_summary, get_settings().PLAN_MAX_TEXT_CHARS, "Plan reasoning")
        current.status = "draft"
        current.updated_at = _now()
        self._save(current)
        self._event(current.id, None, "revised", {"version": current.version})
        return current


plan_manager = PlanManager()
