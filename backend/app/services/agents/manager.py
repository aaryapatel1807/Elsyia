"""Phase 9 local autonomous-agent manager and bounded scheduler."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import uuid
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core import get_settings
from app.services.tools import registry


class AgentError(Exception):
    """Expected agent validation, lifecycle, or budget error."""


AGENT_STATUSES = {"draft", "stopped", "scheduled", "running", "paused", "blocked", "failed", "completed", "expired"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _db_path() -> Path:
    configured = Path(get_settings().AGENTS_DB_PATH)
    path = configured if configured.is_absolute() else Path(__file__).parents[4] / configured
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _bounded(text: str, maximum: int, field: str) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        raise AgentError(f"{field} is required.")
    if len(cleaned) > maximum:
        raise AgentError(f"{field} exceeds the configured limit.")
    return cleaned


@dataclass
class AgentBudget:
    max_runs: int = 100
    max_runtime_seconds: int = 120
    max_tool_calls_per_run: int = 10
    max_browser_requests_per_run: int = 10
    max_file_operations_per_run: int = 10
    max_notifications_per_day: int = 10
    runs_used: int = 0
    notifications_today: int = 0
    budget_day: str = field(default_factory=lambda: _now().date().isoformat())

    def validate(self) -> None:
        settings = get_settings()
        if self.max_runs < 1 or self.max_runs > 10000:
            raise AgentError("max_runs must be between 1 and 10000.")
        if self.max_runtime_seconds < 5 or self.max_runtime_seconds > settings.AGENTS_MAX_RUNTIME_SECONDS:
            raise AgentError("max_runtime_seconds exceeds the global agent limit.")
        if self.max_tool_calls_per_run < 1 or self.max_tool_calls_per_run > settings.AGENTS_MAX_TOOL_CALLS_PER_RUN:
            raise AgentError("max_tool_calls_per_run exceeds the global agent limit.")
        if self.max_notifications_per_day < 0 or self.max_notifications_per_day > settings.AGENTS_MAX_NOTIFICATIONS_PER_DAY:
            raise AgentError("max_notifications_per_day exceeds the global agent limit.")

    def reset_day_if_needed(self) -> None:
        today = _now().date().isoformat()
        if self.budget_day != today:
            self.budget_day = today
            self.notifications_today = 0


@dataclass
class Agent:
    id: str
    name: str
    purpose: str
    status: str = "draft"
    allowed_tools: list[str] = field(default_factory=list)
    allowed_plugins: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    allowed_roots: list[str] = field(default_factory=list)
    interval_seconds: int | None = None
    next_run_at: str | None = None
    max_runs: int = 100
    max_runtime_seconds: int = 120
    max_tool_calls_per_run: int = 10
    max_browser_requests_per_run: int = 10
    max_file_operations_per_run: int = 10
    max_notifications_per_day: int = 10
    runs_used: int = 0
    notifications_today: int = 0
    budget_day: str = field(default_factory=lambda: _now().date().isoformat())
    last_error: str | None = None
    created_at: str = field(default_factory=_iso)
    updated_at: str = field(default_factory=_iso)

    def budget(self) -> AgentBudget:
        return AgentBudget(
            max_runs=self.max_runs,
            max_runtime_seconds=self.max_runtime_seconds,
            max_tool_calls_per_run=self.max_tool_calls_per_run,
            max_browser_requests_per_run=self.max_browser_requests_per_run,
            max_file_operations_per_run=self.max_file_operations_per_run,
            max_notifications_per_day=self.max_notifications_per_day,
            runs_used=self.runs_used,
            notifications_today=self.notifications_today,
            budget_day=self.budget_day,
        )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["budget"] = asdict(self.budget())
        return payload


class AgentManager:
    """Persistent agent store with explicit capability and lifecycle enforcement."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    status TEXT NOT NULL,
                    allowed_tools_json TEXT NOT NULL,
                    allowed_plugins_json TEXT NOT NULL,
                    allowed_domains_json TEXT NOT NULL,
                    allowed_roots_json TEXT NOT NULL,
                    interval_seconds INTEGER,
                    next_run_at TEXT,
                    max_runs INTEGER NOT NULL,
                    max_runtime_seconds INTEGER NOT NULL,
                    max_tool_calls_per_run INTEGER NOT NULL,
                    max_browser_requests_per_run INTEGER NOT NULL,
                    max_file_operations_per_run INTEGER NOT NULL,
                    max_notifications_per_day INTEGER NOT NULL,
                    runs_used INTEGER NOT NULL,
                    notifications_today INTEGER NOT NULL,
                    budget_day TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            connection.commit()

    def _emergency_stopped(self, connection: sqlite3.Connection | None = None) -> bool:
        owned = connection is None
        connection = connection or self._connect()
        try:
            row = connection.execute("SELECT value FROM agent_meta WHERE key = 'emergency_stop'").fetchone()
            return bool(row and row["value"] == "1")
        finally:
            if owned:
                connection.close()

    def _event(self, agent_id: str | None, event_type: str, details: dict[str, Any]) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO agent_events (agent_id, event_type, details_json, created_at) VALUES (?, ?, ?, ?)",
                (agent_id, event_type, json.dumps(details)[:5000], _iso()),
            )
            connection.commit()

    def _validate_capabilities(self, allowed_tools: list[str]) -> list[str]:
        unique = list(dict.fromkeys(item.strip() for item in allowed_tools if item.strip()))
        if len(unique) > 100:
            raise AgentError("An agent may have at most 100 allowed tools.")
        for tool_name in unique:
            if registry.get(tool_name) is None:
                raise AgentError(f"Unknown or unavailable agent tool: {tool_name}")
        return unique

    def create(
        self,
        name: str,
        purpose: str,
        *,
        allowed_tools: list[str] | None = None,
        allowed_plugins: list[str] | None = None,
        allowed_domains: list[str] | None = None,
        allowed_roots: list[str] | None = None,
        interval_seconds: int | None = None,
        budget: AgentBudget | None = None,
    ) -> Agent:
        if not get_settings().AGENTS_ENABLED:
            raise AgentError("Autonomous agents are disabled.")
        if interval_seconds is not None:
            if interval_seconds < get_settings().AGENTS_MIN_INTERVAL_SECONDS:
                raise AgentError("Recurring agent intervals must be at least five minutes.")
            if interval_seconds > 86400:
                raise AgentError("Recurring agent intervals may not exceed one day.")
        selected_budget = budget or AgentBudget(
            max_runtime_seconds=get_settings().AGENTS_MAX_RUNTIME_SECONDS,
            max_tool_calls_per_run=get_settings().AGENTS_MAX_TOOL_CALLS_PER_RUN,
            max_notifications_per_day=get_settings().AGENTS_MAX_NOTIFICATIONS_PER_DAY,
        )
        selected_budget.validate()
        tools = self._validate_capabilities(allowed_tools or [])
        agent = Agent(
            id=uuid.uuid4().hex,
            name=_bounded(name, 120, "Agent name"),
            purpose=_bounded(purpose, 2000, "Agent purpose"),
            allowed_tools=tools,
            allowed_plugins=list(dict.fromkeys(allowed_plugins or []))[:100],
            allowed_domains=list(dict.fromkeys(allowed_domains or []))[:100],
            allowed_roots=list(dict.fromkeys(allowed_roots or []))[:100],
            interval_seconds=interval_seconds,
            max_runs=selected_budget.max_runs,
            max_runtime_seconds=selected_budget.max_runtime_seconds,
            max_tool_calls_per_run=selected_budget.max_tool_calls_per_run,
            max_browser_requests_per_run=selected_budget.max_browser_requests_per_run,
            max_file_operations_per_run=selected_budget.max_file_operations_per_run,
            max_notifications_per_day=selected_budget.max_notifications_per_day,
        )
        self._save(agent)
        self._event(agent.id, "created", {"allowed_tools": len(tools), "interval_seconds": interval_seconds})
        return agent

    def _save(self, agent: Agent) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO agents
                (id, name, purpose, status, allowed_tools_json, allowed_plugins_json, allowed_domains_json,
                 allowed_roots_json, interval_seconds, next_run_at, max_runs, max_runtime_seconds,
                 max_tool_calls_per_run, max_browser_requests_per_run, max_file_operations_per_run,
                 max_notifications_per_day, runs_used, notifications_today, budget_day, last_error,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent.id,
                    agent.name,
                    agent.purpose,
                    agent.status,
                    json.dumps(agent.allowed_tools),
                    json.dumps(agent.allowed_plugins),
                    json.dumps(agent.allowed_domains),
                    json.dumps(agent.allowed_roots),
                    agent.interval_seconds,
                    agent.next_run_at,
                    agent.max_runs,
                    agent.max_runtime_seconds,
                    agent.max_tool_calls_per_run,
                    agent.max_browser_requests_per_run,
                    agent.max_file_operations_per_run,
                    agent.max_notifications_per_day,
                    agent.runs_used,
                    agent.notifications_today,
                    agent.budget_day,
                    agent.last_error,
                    agent.created_at,
                    agent.updated_at,
                ),
            )
            connection.commit()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Agent:
        return Agent(
            id=row["id"],
            name=row["name"],
            purpose=row["purpose"],
            status=row["status"],
            allowed_tools=json.loads(row["allowed_tools_json"]),
            allowed_plugins=json.loads(row["allowed_plugins_json"]),
            allowed_domains=json.loads(row["allowed_domains_json"]),
            allowed_roots=json.loads(row["allowed_roots_json"]),
            interval_seconds=row["interval_seconds"],
            next_run_at=row["next_run_at"],
            max_runs=row["max_runs"],
            max_runtime_seconds=row["max_runtime_seconds"],
            max_tool_calls_per_run=row["max_tool_calls_per_run"],
            max_browser_requests_per_run=row["max_browser_requests_per_run"],
            max_file_operations_per_run=row["max_file_operations_per_run"],
            max_notifications_per_day=row["max_notifications_per_day"],
            runs_used=row["runs_used"],
            notifications_today=row["notifications_today"],
            budget_day=row["budget_day"],
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get(self, agent_id: str) -> Agent:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if row is None:
            raise AgentError("Agent was not found.")
        return self._from_row(row)

    def list(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM agents ORDER BY updated_at DESC LIMIT 100").fetchall()
        return [self._from_row(row).as_dict() for row in rows]

    def _set_status(self, agent: Agent, status: str) -> Agent:
        if status not in AGENT_STATUSES:
            raise AgentError(f"Unsupported agent state: {status}")
        agent.status = status
        agent.updated_at = _iso()
        self._save(agent)
        self._event(agent.id, status, {})
        return agent

    def start(self, agent_id: str) -> Agent:
        agent = self.get(agent_id)
        if self._emergency_stopped():
            raise AgentError("Global agent emergency stop is active.")
        if agent.status not in {"draft", "stopped", "paused", "failed"}:
            raise AgentError("Agent cannot be started from its current state.")
        agent.next_run_at = _iso(_now())
        return self._set_status(agent, "scheduled")

    def pause(self, agent_id: str) -> Agent:
        agent = self.get(agent_id)
        if agent.status not in {"scheduled", "running"}:
            raise AgentError("Only scheduled or running agents can be paused.")
        return self._set_status(agent, "paused")

    def stop(self, agent_id: str) -> Agent:
        agent = self.get(agent_id)
        if agent.status in {"completed", "expired"}:
            raise AgentError("Agent is already terminal.")
        agent.next_run_at = None
        return self._set_status(agent, "stopped")

    def emergency_stop(self) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            connection.execute("INSERT OR REPLACE INTO agent_meta (key, value) VALUES ('emergency_stop', '1')")
            connection.execute(
                "UPDATE agents SET status = 'paused', updated_at = ? WHERE status IN ('scheduled', 'running')",
                (_iso(),),
            )
            connection.commit()
        self._event(None, "emergency_stop", {"active": True})
        return {"active": True, "status": "stopped"}

    def clear_emergency_stop(self) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            connection.execute("DELETE FROM agent_meta WHERE key = 'emergency_stop'")
            connection.commit()
        self._event(None, "emergency_stop_cleared", {"active": False})
        return {"active": False, "status": "cleared"}

    def emergency_stop_status(self) -> bool:
        with self._lock:
            return self._emergency_stopped()

    def record_notification(self, agent_id: str) -> bool:
        """Consume one daily notification budget unit, failing closed at the limit."""
        agent = self.get(agent_id)
        budget = agent.budget()
        budget.reset_day_if_needed()
        if budget.notifications_today >= budget.max_notifications_per_day:
            self._event(agent.id, "notification_budget_blocked", {})
            return False
        agent.notifications_today = budget.notifications_today + 1
        agent.budget_day = budget.budget_day
        agent.updated_at = _iso()
        self._save(agent)
        return True

    def _budget_block(self, agent: Agent) -> str | None:
        budget = agent.budget()
        budget.reset_day_if_needed()
        if budget.runs_used >= budget.max_runs:
            return "Agent run budget is exhausted."
        if budget.notifications_today > budget.max_notifications_per_day:
            return "Agent notification budget is exhausted."
        return None

    def prepare_run(self, agent_id: str, *, force: bool = False) -> dict[str, Any]:
        agent = self.get(agent_id)
        if self._emergency_stopped():
            raise AgentError("Global agent emergency stop is active.")
        if agent.status not in {"scheduled", "stopped", "failed"}:
            raise AgentError("Agent is not eligible for a run.")
        if not force and agent.next_run_at:
            due = datetime.fromisoformat(agent.next_run_at)
            if due > _now():
                return {"status": "waiting", "agent": agent.as_dict(), "next_run_at": agent.next_run_at}
        budget_error = self._budget_block(agent)
        if budget_error:
            agent.status = "blocked"
            agent.last_error = budget_error
            self._save(agent)
            self._event(agent.id, "budget_blocked", {"error": budget_error})
            return {"status": "blocked", "agent": agent.as_dict(), "error": budget_error}
        agent.status = "running"
        agent.runs_used += 1
        agent.last_error = None
        agent.next_run_at = None
        agent.updated_at = _iso()
        self._save(agent)
        run_id = uuid.uuid4().hex
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO agent_runs (id, agent_id, status, started_at, details_json) VALUES (?, ?, ?, ?, ?)",
                (run_id, agent.id, "prepared", _iso(), json.dumps({"allowed_tools": agent.allowed_tools})),
            )
            connection.commit()
        self._event(agent.id, "run_prepared", {"run_id": run_id, "allowed_tools": agent.allowed_tools})
        return {
            "status": "prepared",
            "run_id": run_id,
            "agent": agent.as_dict(),
            "confirmation_required": False,
            "message": "Run prepared; no tool has been executed.",
        }

    def scheduler_tick(self) -> list[dict[str, Any]]:
        if not get_settings().AGENTS_ENABLED or self._emergency_stopped():
            return []
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM agents WHERE status = 'scheduled' AND next_run_at IS NOT NULL ORDER BY next_run_at LIMIT ?",
                (get_settings().AGENTS_MAX_ACTIVE,),
            ).fetchall()
        prepared: list[dict[str, Any]] = []
        for row in rows:
            agent = self._from_row(row)
            result = self.prepare_run(agent.id)
            prepared.append(result)
            refreshed = self.get(agent.id)
            if refreshed.interval_seconds and result.get("status") == "prepared":
                refreshed.status = "scheduled"
                refreshed.next_run_at = _iso(_now() + timedelta(seconds=refreshed.interval_seconds))
                refreshed.updated_at = _iso()
                self._save(refreshed)
        return prepared

    def events(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            if agent_id:
                rows = connection.execute(
                    "SELECT agent_id, event_type, details_json, created_at FROM agent_events WHERE agent_id = ? ORDER BY id DESC LIMIT 100",
                    (agent_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT agent_id, event_type, details_json, created_at FROM agent_events ORDER BY id DESC LIMIT 100"
                ).fetchall()
        return [
            {
                "agent_id": row["agent_id"],
                "event_type": row["event_type"],
                "details": json.loads(row["details_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]


async def agent_scheduler_worker(stop_event: asyncio.Event) -> None:
    """Prepare due agent runs without executing tools or bypassing confirmations."""
    settings = get_settings()
    while not stop_event.is_set():
        if settings.AGENTS_WORKER_ENABLED:
            try:
                agent_manager.scheduler_tick()
                from app.services.agents.monitoring import monitor_manager

                monitor_manager.evaluate()
            except Exception:
                # A malformed agent or monitor must not terminate the shared backend worker.
                pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.AGENTS_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass


agent_manager = AgentManager()
