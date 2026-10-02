"""Local-first enterprise workspace, policy, audit, and analytics manager."""

from __future__ import annotations

import hmac
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core import get_logger, get_settings

logger = get_logger("enterprise.manager")
_ROLES = {"owner", "admin", "member", "viewer"}
_MEMBER_STATUSES = {"active", "pending", "disabled"}
_POLICY_DEFAULTS = {
    "require_confirmation_for_risky_tools": True,
    "allow_cloud_sync": False,
    "allow_autonomous_agents": True,
    "allow_browser_automation": True,
    "allow_desktop_automation": True,
    "analytics_opt_in": False,
}


class EnterpriseError(ValueError):
    """Raised for invalid enterprise settings, roles, or policy operations."""


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class WorkspaceMember:
    id: str
    display_name: str
    role: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EnterprisePolicy:
    key: str
    enabled: bool
    updated_at: str


class EnterpriseManager:
    """SQLite-backed local administration boundary."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.project_root = Path(__file__).parents[4].resolve()
        raw_path = Path(self.settings.ENTERPRISE_DB_PATH)
        self.db_path = raw_path.resolve() if raw_path.is_absolute() else (self.project_root / raw_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _initialize(self) -> None:
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workspace (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS members (id TEXT PRIMARY KEY, display_name TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS policies (key TEXT PRIMARY KEY, enabled INTEGER NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS analytics (event_key TEXT PRIMARY KEY, count INTEGER NOT NULL, first_at TEXT NOT NULL, last_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS admin_events (id TEXT PRIMARY KEY, action TEXT NOT NULL, target_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, principal_id TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS mfa_enrollments (id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, provider TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS invitations (id TEXT PRIMARY KEY, display_name TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, status TEXT NOT NULL, accepted_member_id TEXT)"
            )
            if connection.execute("SELECT 1 FROM workspace WHERE id = ?", (self.settings.ENTERPRISE_WORKSPACE_ID,)).fetchone() is None:
                connection.execute(
                    "INSERT INTO workspace(id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (self.settings.ENTERPRISE_WORKSPACE_ID, self.settings.ENTERPRISE_WORKSPACE_NAME, now, now),
                )
            if connection.execute("SELECT 1 FROM members WHERE role = 'owner'").fetchone() is None:
                member_id = str(uuid4())
                connection.execute(
                    "INSERT INTO members(id, display_name, role, status, created_at, updated_at) VALUES (?, ?, 'owner', 'active', ?, ?)",
                    (member_id, "Local Owner", now, now),
                )
            for key, enabled in _POLICY_DEFAULTS.items():
                connection.execute(
                    "INSERT OR IGNORE INTO policies(key, enabled, updated_at) VALUES (?, ?, ?)",
                    (key, int(enabled), now),
                )
            connection.commit()

    def require_admin(self, token: str | None) -> None:
        configured = self.settings.ENTERPRISE_ADMIN_TOKEN.strip()
        if not configured:
            raise EnterpriseError("Enterprise administration is locked; set ENTERPRISE_ADMIN_TOKEN in .env")
        if not token or not hmac.compare_digest(token, configured):
            raise EnterpriseError("Enterprise administration token is invalid")

    @staticmethod
    def _workspace(row: sqlite3.Row) -> Workspace:
        return Workspace(row["id"], row["name"], row["created_at"], row["updated_at"])

    @staticmethod
    def _member(row: sqlite3.Row) -> WorkspaceMember:
        return WorkspaceMember(row["id"], row["display_name"], row["role"], row["status"], row["created_at"], row["updated_at"])

    def get_workspace(self) -> Workspace:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM workspace WHERE id = ?", (self.settings.ENTERPRISE_WORKSPACE_ID,)).fetchone()
        if row is None:
            raise EnterpriseError("Workspace is not initialized")
        return self._workspace(row)

    def update_workspace(self, name: str) -> Workspace:
        normalized = " ".join(name.strip().split())
        if not normalized or len(normalized) > 200:
            raise EnterpriseError("Workspace name must contain 1-200 characters")
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute("UPDATE workspace SET name = ?, updated_at = ? WHERE id = ?", (normalized, now, self.settings.ENTERPRISE_WORKSPACE_ID))
            connection.commit()
        self.record_admin_event("workspace.update", "workspace", "success")
        return self.get_workspace()

    def list_members(self) -> list[WorkspaceMember]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM members ORDER BY role, display_name").fetchall()
        return [self._member(row) for row in rows]

    def add_member(self, display_name: str, role: str = "member", member_status: str = "active") -> WorkspaceMember:
        normalized_name = " ".join(display_name.strip().split())
        if not normalized_name or len(normalized_name) > 200:
            raise EnterpriseError("Member display name must contain 1-200 characters")
        if role not in _ROLES - {"owner"}:
            raise EnterpriseError("New members may use admin, member, or viewer roles")
        if member_status not in _MEMBER_STATUSES - {"disabled"}:
            raise EnterpriseError("New members may use active or pending status")
        if len(self.list_members()) >= self.settings.ENTERPRISE_MAX_MEMBERS:
            raise EnterpriseError("Workspace member limit reached")
        now = self._now()
        member_id = str(uuid4())
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO members(id, display_name, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (member_id, normalized_name, role, member_status, now, now),
            )
            connection.commit()
        self.record_admin_event("member.create", "member", "success")
        return self.get_member(member_id)

    def get_member(self, member_id: str) -> WorkspaceMember:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if row is None:
            raise EnterpriseError("Member not found")
        return self._member(row)

    def update_member(self, member_id: str, *, role: str | None = None, status: str | None = None) -> WorkspaceMember:
        member = self.get_member(member_id)
        next_role = role if role is not None else member.role
        next_status = status if status is not None else member.status
        if next_role not in _ROLES or next_status not in _MEMBER_STATUSES:
            raise EnterpriseError("Invalid member role or status")
        if member.role == "owner" and next_role != "owner":
            raise EnterpriseError("The workspace owner role cannot be reassigned in the local MVP")
        if member.role == "owner" and next_status == "disabled":
            raise EnterpriseError("The workspace owner cannot be disabled")
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute("UPDATE members SET role = ?, status = ?, updated_at = ? WHERE id = ?", (next_role, next_status, now, member_id))
            connection.commit()
        self.record_admin_event("member.update", "member", "success")
        return self.get_member(member_id)

    def delete_member(self, member_id: str) -> None:
        member = self.get_member(member_id)
        if member.role == "owner":
            raise EnterpriseError("The workspace owner cannot be deleted")
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM members WHERE id = ?", (member_id,))
            connection.commit()
        self.record_admin_event("member.delete", "member", "success")

    def create_invitation(self, session_token: str, display_name: str, role: str = "member", ttl_hours: int = 72) -> dict[str, Any]:
        session = self.require_session(session_token)
        normalized_name = " ".join(display_name.strip().split())
        if not normalized_name or len(normalized_name) > 200:
            raise EnterpriseError("Invitation display name must contain 1-200 characters")
        if role not in _ROLES - {"owner"}:
            raise EnterpriseError("Invitations may use admin, member, or viewer roles")
        if ttl_hours < 1 or ttl_hours > 168:
            raise EnterpriseError("Invitation expiry must be between 1 and 168 hours")
        if len(self.list_members()) >= self.settings.ENTERPRISE_MAX_MEMBERS:
            raise EnterpriseError("Workspace member limit reached")
        invitation_id = str(uuid4())
        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl_hours)
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO invitations(id, display_name, role, token_hash, created_at, expires_at, status, accepted_member_id) VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)",
                (invitation_id, normalized_name, role, self._token_hash(raw_token), now.isoformat(), expires.isoformat()),
            )
            connection.commit()
        self.record_admin_event("invitation.create", "invitation", "success")
        return {"id": invitation_id, "display_name": normalized_name, "role": role, "status": "pending", "created_at": now.isoformat(), "expires_at": expires.isoformat(), "invitation_token": raw_token, "created_by": session["principal_id"]}

    def list_invitations(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        with closing(self._connect()) as connection:
            connection.execute("UPDATE invitations SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?", (now.isoformat(),))
            rows = connection.execute("SELECT id, display_name, role, created_at, expires_at, status, accepted_member_id FROM invitations ORDER BY created_at DESC").fetchall()
            connection.commit()
        return [dict(row) for row in rows]

    def revoke_invitation(self, invitation_id: str) -> None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT status FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
            if row is None:
                raise EnterpriseError("Invitation not found")
            if row["status"] != "pending":
                raise EnterpriseError("Only pending invitations can be revoked")
            connection.execute("UPDATE invitations SET status = 'revoked' WHERE id = ?", (invitation_id,))
            connection.commit()
        self.record_admin_event("invitation.revoke", "invitation", "success")

    def accept_invitation(self, invitation_token: str) -> WorkspaceMember:
        if not invitation_token or len(invitation_token) > 256:
            raise EnterpriseError("Invitation token is invalid")
        now = datetime.now(timezone.utc)
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM invitations WHERE token_hash = ?", (self._token_hash(invitation_token),)).fetchone()
            if row is None:
                raise EnterpriseError("Invitation token is invalid")
            if row["status"] != "pending":
                raise EnterpriseError("Invitation is no longer pending")
            if datetime.fromisoformat(row["expires_at"]) <= now:
                connection.execute("UPDATE invitations SET status = 'expired' WHERE id = ?", (row["id"],))
                connection.commit()
                raise EnterpriseError("Invitation has expired")
        member = self.add_member(row["display_name"], row["role"], member_status="pending")
        with closing(self._connect()) as connection:
            connection.execute("UPDATE invitations SET status = 'accepted', accepted_member_id = ? WHERE id = ?", (member.id, row["id"]))
            connection.commit()
        self.record_admin_event("invitation.accept", "invitation", "success")
        return member

    def list_policies(self) -> list[EnterprisePolicy]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM policies ORDER BY key").fetchall()
        return [EnterprisePolicy(row["key"], bool(row["enabled"]), row["updated_at"]) for row in rows]

    def policy_enabled(self, key: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT enabled FROM policies WHERE key = ?", (key,)).fetchone()
        return bool(row["enabled"]) if row is not None else bool(_POLICY_DEFAULTS.get(key, False))

    def set_policy(self, key: str, enabled: bool) -> EnterprisePolicy:
        if key not in _POLICY_DEFAULTS:
            raise EnterpriseError("Unknown enterprise policy")
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO policies(key, enabled, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at",
                (key, int(enabled), now),
            )
            connection.commit()
        self.record_admin_event("policy.update", "policy", "success")
        return next(item for item in self.list_policies() if item.key == key)

    def record_admin_event(self, action: str, target_type: str, status: str) -> None:
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO admin_events(id, action, target_type, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (secrets.token_hex(16), action[:80], target_type[:50], status[:30], now),
            )
            connection.commit()

    def record_analytics(self, event_key: str) -> None:
        if not self.policy_enabled("analytics_opt_in"):
            return
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO analytics(event_key, count, first_at, last_at) VALUES (?, 1, ?, ?) ON CONFLICT(event_key) DO UPDATE SET count = count + 1, last_at = excluded.last_at",
                (event_key[:80], now, now),
            )
            connection.commit()

    def analytics(self) -> dict[str, Any]:
        if not self.policy_enabled("analytics_opt_in"):
            return {"enabled": False, "events": []}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.settings.ENTERPRISE_ANALYTICS_RETENTION_DAYS)).isoformat()
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM analytics WHERE last_at < ?", (cutoff,))
            rows = connection.execute("SELECT event_key, count, first_at, last_at FROM analytics ORDER BY last_at DESC").fetchall()
            connection.commit()
        return {
            "enabled": True,
            "events": [
                {"event": row["event_key"], "count": row["count"], "first_at": row["first_at"], "last_at": row["last_at"]}
                for row in rows
            ],
        }

    def audit_summary(self) -> dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.settings.ENTERPRISE_AUDIT_RETENTION_DAYS)).isoformat()
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM admin_events WHERE created_at < ?", (cutoff,))
            rows = connection.execute("SELECT action, status, COUNT(*) AS count FROM admin_events GROUP BY action, status ORDER BY count DESC").fetchall()
            latest = connection.execute("SELECT action, status, created_at FROM admin_events ORDER BY created_at DESC LIMIT 20").fetchall()
            connection.commit()
        return {
            "events": [{"action": row["action"], "status": row["status"], "count": row["count"]} for row in rows],
            "recent": [{"action": row["action"], "status": row["status"], "created_at": row["created_at"]} for row in latest],
            "retention_days": self.settings.ENTERPRISE_AUDIT_RETENTION_DAYS,
        }

    def _session_key(self) -> bytes:
        key = self.settings.ENTERPRISE_SESSION_SIGNING_KEY.strip()
        if not key:
            raise EnterpriseError("Session signing is not configured; set ENTERPRISE_SESSION_SIGNING_KEY in .env")
        return key.encode("utf-8")

    @staticmethod
    def _token_hash(token: str) -> str:
        import hashlib
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _owner(self) -> WorkspaceMember:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM members WHERE role = 'owner' LIMIT 1").fetchone()
        if row is None:
            raise EnterpriseError("Workspace owner is not initialized")
        return self._member(row)

    def create_session(self, admin_token: str) -> dict[str, Any]:
        self.require_admin(admin_token)
        session_id = str(uuid4())
        created = datetime.now(timezone.utc)
        expires = created + timedelta(minutes=self.settings.ENTERPRISE_SESSION_TTL_MINUTES)
        payload = f"{session_id}.{int(expires.timestamp())}.{secrets.token_urlsafe(24)}"
        signature = hmac.new(self._session_key(), payload.encode("utf-8"), "sha256").hexdigest()
        session_token = f"{payload}.{signature}"
        owner = self._owner()
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO sessions(id, token_hash, principal_id, role, created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (session_id, self._token_hash(session_token), owner.id, owner.role, created.isoformat(), expires.isoformat()),
            )
            connection.commit()
        self.record_admin_event("auth.session.create", "session", "success")
        return {"session_token": session_token, "session_id": session_id, "principal_id": owner.id, "role": owner.role, "expires_at": expires.isoformat()}

    def _verify_session(self, session_token: str) -> dict[str, Any]:
        parts = session_token.split(".")
        if len(parts) != 4:
            raise EnterpriseError("Session token is invalid")
        payload = ".".join(parts[:3])
        expected = hmac.new(self._session_key(), payload.encode("utf-8"), "sha256").hexdigest()
        if not hmac.compare_digest(parts[3], expected):
            raise EnterpriseError("Session token is invalid")
        try:
            expires_epoch = int(parts[1])
        except ValueError as exc:
            raise EnterpriseError("Session token is invalid") from exc
        now = datetime.now(timezone.utc)
        if expires_epoch <= int(now.timestamp()):
            raise EnterpriseError("Session token has expired")
        session_id = parts[0]
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ? AND token_hash = ?", (session_id, self._token_hash(session_token))).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise EnterpriseError("Session token is revoked or unknown")
        if datetime.fromisoformat(row["expires_at"]) <= now:
            raise EnterpriseError("Session token has expired")
        return {"session_id": row["id"], "principal_id": row["principal_id"], "role": row["role"], "created_at": row["created_at"], "expires_at": row["expires_at"]}

    def require_session(self, session_token: str | None) -> dict[str, Any]:
        if not session_token:
            raise EnterpriseError("Bearer session is required")
        return self._verify_session(session_token)

    def revoke_session(self, session_token: str) -> None:
        session = self._verify_session(session_token)
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (now, session["session_id"]))
            connection.commit()
        self.record_admin_event("auth.session.revoke", "session", "success")

    def auth_status(self) -> dict[str, Any]:
        return {
            "admin_token_configured": bool(self.settings.ENTERPRISE_ADMIN_TOKEN.strip()),
            "session_signing_key_configured": bool(self.settings.ENTERPRISE_SESSION_SIGNING_KEY.strip()),
            "sso_enabled": self.settings.ENTERPRISE_SSO_ENABLED,
            "sso_configured": bool(self.settings.ENTERPRISE_SSO_ISSUER.strip() and self.settings.ENTERPRISE_SSO_CLIENT_ID.strip() and self.settings.ENTERPRISE_SSO_REDIRECT_URI.strip()),
            "mfa_readiness_enabled": self.settings.ENTERPRISE_MFA_READINESS_ENABLED,
        }

    def enroll_mfa(self, session_token: str) -> dict[str, Any]:
        session = self.require_session(session_token)
        if not self.settings.ENTERPRISE_MFA_READINESS_ENABLED:
            raise EnterpriseError("MFA readiness is disabled")
        now = self._now()
        enrollment_id = str(uuid4())
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT INTO mfa_enrollments(id, principal_id, provider, status, created_at, updated_at) VALUES (?, ?, 'provider_pending', 'pending_provider_setup', ?, ?)",
                (enrollment_id, session["principal_id"], now, now),
            )
            connection.commit()
        self.record_admin_event("auth.mfa.enroll", "mfa", "pending")
        return {"enrollment_id": enrollment_id, "principal_id": session["principal_id"], "provider": "provider_pending", "status": "pending_provider_setup"}

    def status(self) -> dict[str, Any]:
        members = self.list_members()
        return {
            "enabled": self.settings.ENTERPRISE_ENABLED,
            "workspace": self.get_workspace(),
            "member_count": len(members),
            "analytics_opt_in": self.policy_enabled("analytics_opt_in"),
            "admin_auth_configured": bool(self.settings.ENTERPRISE_ADMIN_TOKEN.strip()),
        }


_manager: EnterpriseManager | None = None


def get_enterprise_manager() -> EnterpriseManager:
    global _manager
    if _manager is None:
        _manager = EnterpriseManager()
    return _manager


__all__ = [
    "EnterpriseError",
    "EnterpriseManager",
    "EnterprisePolicy",
    "Workspace",
    "WorkspaceMember",
    "get_enterprise_manager",
]
