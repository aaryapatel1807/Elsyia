"""Local file/metric monitor triggers and notification policy for Phase 9."""

from __future__ import annotations

import json
import operator
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core import get_settings
from app.services.agents.manager import AgentError, AgentManager, agent_manager


class MonitorError(Exception):
    """Expected monitor validation or persistence error."""


_OPERATORS = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt, "lte": operator.le, "eq": operator.eq}
_METRICS = {"runs_used", "notifications_today", "active"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_path() -> Path:
    configured = Path(get_settings().AGENTS_DB_PATH)
    path = configured if configured.is_absolute() else Path(__file__).parents[4] / configured
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class NotificationStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._lock = threading.RLock()
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, title TEXT NOT NULL,
                    body TEXT NOT NULL, severity TEXT NOT NULL, source TEXT NOT NULL,
                    created_at TEXT NOT NULL, read_at TEXT
                )"""
            )
            connection.commit()

    def create(self, agent_id: str, title: str, body: str, *, severity: str, source: str) -> dict[str, Any]:
        title = " ".join(title.strip().split())[:200]
        body = " ".join(body.strip().split())[:2000]
        if not title or not body or severity not in {"info", "warning", "critical"}:
            raise MonitorError("Notification content or severity is invalid.")
        notification = {
            "id": uuid.uuid4().hex,
            "agent_id": agent_id,
            "title": title,
            "body": body,
            "severity": severity,
            "source": source[:120],
            "created_at": _now(),
            "read_at": None,
        }
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            connection.execute(
                "INSERT INTO notifications (id, agent_id, title, body, severity, source, created_at, read_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                tuple(notification[key] for key in ("id", "agent_id", "title", "body", "severity", "source", "created_at")),
            )
            connection.commit()
        return notification

    def list(self, *, unread_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM notifications"
        if unread_only:
            query += " WHERE read_at IS NULL"
        query += " ORDER BY created_at DESC LIMIT 100"
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    def mark_read(self, notification_id: str) -> bool:
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            result = connection.execute(
                "UPDATE notifications SET read_at = ? WHERE id = ? AND read_at IS NULL", (_now(), notification_id)
            )
            connection.commit()
            return result.rowcount == 1


class MonitorManager:
    """Evaluate approved local monitors and emit deduplicated in-app notifications."""

    def __init__(self, db_path: Path | None = None, agents: AgentManager | None = None) -> None:
        self._db_path = db_path or _db_path()
        self._agents = agents or agent_manager
        self.notifications = NotificationStore(self._db_path)
        self._lock = threading.RLock()
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS monitors (
                    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, kind TEXT NOT NULL,
                    config_json TEXT NOT NULL, last_state TEXT, enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )"""
            )
            connection.commit()

    def _within_allowed_root(self, path: Path, roots: list[str]) -> bool:
        if path.is_symlink():
            return False
        resolved = path.resolve()
        for raw in roots:
            root = Path(raw).expanduser().resolve()
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def create(self, agent_id: str, kind: str, config: dict[str, Any]) -> dict[str, Any]:
        agent = self._agents.get(agent_id)
        if kind not in {"file", "metric"}:
            raise MonitorError("Monitor kind must be file or metric.")
        if kind == "file":
            raw_path = str(config.get("path", "")).strip()
            path = Path(raw_path).expanduser()
            if not path.is_file() or not self._within_allowed_root(path, agent.allowed_roots):
                raise MonitorError("File monitors require an existing non-symlink file inside an agent allowed root.")
            normalized = {"path": str(path.resolve())}
        else:
            metric = str(config.get("metric", "")).strip()
            operator_name = str(config.get("operator", "eq")).strip().lower()
            if metric not in _METRICS or operator_name not in _OPERATORS:
                raise MonitorError("Metric or comparison operator is not allowlisted.")
            try:
                threshold = float(config.get("threshold"))
            except (TypeError, ValueError) as exc:
                raise MonitorError("Metric threshold must be numeric.") from exc
            normalized = {"metric": metric, "operator": operator_name, "threshold": threshold}
        monitor = {"id": uuid.uuid4().hex, "agent_id": agent_id, "kind": kind, "config": normalized, "last_state": None, "enabled": True, "created_at": _now(), "updated_at": _now()}
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            connection.execute(
                "INSERT INTO monitors (id, agent_id, kind, config_json, last_state, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, NULL, 1, ?, ?)",
                (monitor["id"], agent_id, kind, json.dumps(normalized), monitor["created_at"], monitor["updated_at"]),
            )
            connection.commit()
        return monitor

    def list(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM monitors"
        args: tuple[Any, ...] = ()
        if agent_id:
            query += " WHERE agent_id = ?"
            args = (agent_id,)
        query += " ORDER BY created_at DESC LIMIT 100"
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, args).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {"id": row["id"], "agent_id": row["agent_id"], "kind": row["kind"], "config": json.loads(row["config_json"]), "last_state": json.loads(row["last_state"]) if row["last_state"] else None, "enabled": bool(row["enabled"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def _emit(self, agent_id: str, monitor_id: str, state: dict[str, Any]) -> dict[str, Any] | None:
        if not self._agents.record_notification(agent_id):
            return None
        notification = self.notifications.create(
            agent_id,
            "Agent monitor triggered",
            json.dumps(state, sort_keys=True)[:1800],
            severity="info",
            source=f"monitor:{monitor_id}",
        )
        return notification

    def evaluate(self, metrics: dict[str, float] | None = None) -> list[dict[str, Any]]:
        metrics = metrics or {}
        candidates: list[tuple[str, str, dict[str, Any]]] = []
        with self._lock, closing(sqlite3.connect(self._db_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM monitors WHERE enabled = 1 ORDER BY created_at LIMIT 100").fetchall()
            for row in rows:
                config = json.loads(row["config_json"])
                if row["kind"] == "file":
                    path = Path(config["path"])
                    if path.is_symlink() or not path.is_file():
                        state = {"exists": False}
                    else:
                        stat = path.stat()
                        state = {"exists": True, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
                else:
                    metric = config["metric"]
                    value = float(metrics.get(metric, 0))
                    state = {"metric": metric, "value": value, "matched": bool(_OPERATORS[config["operator"]](value, config["threshold"]))}
                previous = json.loads(row["last_state"]) if row["last_state"] else None
                connection.execute("UPDATE monitors SET last_state = ?, updated_at = ? WHERE id = ?", (json.dumps(state), _now(), row["id"]))
                if previous is not None and previous != state:
                    candidates.append((row["agent_id"], row["id"], state))
            connection.commit()
        emitted: list[dict[str, Any]] = []
        for agent_id, monitor_id, state in candidates:
            notification = self._emit(agent_id, monitor_id, state)
            if notification:
                emitted.append(notification)
        return emitted


monitor_manager = MonitorManager()
