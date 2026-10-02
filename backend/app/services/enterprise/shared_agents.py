"""Local shared-agent grants for the Phase 12 enterprise boundary."""

from __future__ import annotations

import json
import sqlite3
import secrets
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core import get_settings
from app.services.agents import agent_manager
from app.services.enterprise.manager import EnterpriseError, EnterpriseManager, get_enterprise_manager

_ALLOWED = {"view", "prepare_run"}


class SharedAgentError(EnterpriseError):
    """Expected shared-agent authorization error."""


class SharedAgentManager:
    def __init__(self, enterprise: EnterpriseManager | None = None) -> None:
        self.enterprise = enterprise or get_enterprise_manager()
        self.db_path = self.enterprise.db_path
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS agent_grants (
                id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, member_id TEXT NOT NULL,
                capabilities_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
                revoked_at TEXT
            )""")
            connection.commit()

    def _authorize(self, session_token: str, *, write: bool = False) -> dict[str, Any]:
        session = self.enterprise.require_session(session_token)
        if session["role"] not in {"owner", "admin"} and write:
            raise SharedAgentError("Only workspace administrators may change shared-agent grants")
        member = self.enterprise.get_member(session["principal_id"])
        if member.status != "active":
            raise SharedAgentError("Inactive members cannot use shared-agent grants")
        return session

    def grant(self, session_token: str, agent_id: str, member_id: str, capabilities: list[str]) -> dict[str, Any]:
        self._authorize(session_token, write=True)
        agent_manager.get(agent_id)
        member = self.enterprise.get_member(member_id)
        if member.status != "active":
            raise SharedAgentError("Grants may target active workspace members only")
        selected = sorted(set(capabilities))
        if not selected or not set(selected).issubset(_ALLOWED):
            raise SharedAgentError("Shared-agent capabilities are limited to view and prepare_run")
        now = datetime.now(timezone.utc).isoformat()
        record = {"id": secrets.token_urlsafe(16), "agent_id": agent_id, "member_id": member_id, "capabilities": selected, "status": "active", "created_at": now, "revoked_at": None}
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("INSERT INTO agent_grants VALUES (?, ?, ?, ?, ?, ?, NULL)", (record["id"], agent_id, member_id, json.dumps(selected), "active", now))
            connection.commit()
        self.enterprise.record_admin_event("shared_agent.grant", "agent_grant", "success")
        return record

    def list(self, session_token: str, agent_id: str | None = None) -> list[dict[str, Any]]:
        self._authorize(session_token)
        query = "SELECT * FROM agent_grants WHERE status = 'active'"
        params: tuple[Any, ...] = ()
        if agent_id:
            query += " AND agent_id = ?"
            params = (agent_id,)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()
        return [{"id": row["id"], "agent_id": row["agent_id"], "member_id": row["member_id"], "capabilities": json.loads(row["capabilities_json"]), "status": row["status"], "created_at": row["created_at"], "revoked_at": row["revoked_at"]} for row in rows]

    def revoke(self, session_token: str, grant_id: str) -> None:
        self._authorize(session_token, write=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            result = connection.execute("UPDATE agent_grants SET status = 'revoked', revoked_at = ? WHERE id = ? AND status = 'active'", (datetime.now(timezone.utc).isoformat(), grant_id))
            connection.commit()
        if result.rowcount != 1:
            raise SharedAgentError("Active shared-agent grant was not found")
        self.enterprise.record_admin_event("shared_agent.revoke", "agent_grant", "success")

    def authorize(self, session_token: str, agent_id: str, capability: str) -> bool:
        session = self._authorize(session_token)
        with closing(sqlite3.connect(self.db_path)) as connection:
            row = connection.execute("SELECT capabilities_json FROM agent_grants WHERE agent_id = ? AND member_id = ? AND status = 'active'", (agent_id, session["principal_id"])).fetchone()
        return bool(row and capability in json.loads(row[0]))


shared_agent_manager = SharedAgentManager()
