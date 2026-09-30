"""Regression tests for Phase 12 local workspace invitations."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.api.v1 import collaboration  # noqa: E402
import app.services.enterprise.manager as enterprise_module  # noqa: E402
from app.services.enterprise import EnterpriseError, EnterpriseManager  # noqa: E402


class Phase12CollaborationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = get_settings()
        self.settings.ENTERPRISE_DB_PATH = str(root / "enterprise.db")
        self.settings.ENTERPRISE_WORKSPACE_ID = "collab-workspace"
        self.settings.ENTERPRISE_WORKSPACE_NAME = "Collaboration Workspace"
        self.settings.ENTERPRISE_ADMIN_TOKEN = "bootstrap"
        self.settings.ENTERPRISE_SESSION_SIGNING_KEY = "collaboration-session-key"
        self.settings.ENTERPRISE_MAX_MEMBERS = 10
        self.manager = EnterpriseManager()
        enterprise_module._manager = self.manager
        self.session = self.manager.create_session("bootstrap")["session_token"]

    def tearDown(self) -> None:
        enterprise_module._manager = None
        self.temp.cleanup()

    def test_invitation_token_is_hashed_and_one_time(self) -> None:
        invitation = self.manager.create_invitation(self.session, "Alice", "member", ttl_hours=24)
        self.assertTrue(invitation["invitation_token"])
        connection = sqlite3.connect(self.settings.ENTERPRISE_DB_PATH)
        try:
            row = connection.execute("SELECT token_hash FROM invitations WHERE id = ?", (invitation["id"],)).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(row)
        self.assertNotIn(invitation["invitation_token"], row[0])
        member = self.manager.accept_invitation(invitation["invitation_token"])
        self.assertEqual(member.status, "pending")
        with self.assertRaises(EnterpriseError):
            self.manager.accept_invitation(invitation["invitation_token"])
        self.assertEqual(self.manager.list_invitations()[0]["status"], "accepted")

    def test_revoke_invitation_blocks_acceptance(self) -> None:
        invitation = self.manager.create_invitation(self.session, "Bob", "viewer")
        self.manager.revoke_invitation(invitation["id"])
        with self.assertRaises(EnterpriseError):
            self.manager.accept_invitation(invitation["invitation_token"])

    def test_expired_invitation_is_rejected(self) -> None:
        invitation = self.manager.create_invitation(self.session, "Carol", "member", ttl_hours=1)
        connection = sqlite3.connect(self.settings.ENTERPRISE_DB_PATH)
        try:
            connection.execute("UPDATE invitations SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (invitation["id"],))
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(EnterpriseError):
            self.manager.accept_invitation(invitation["invitation_token"])
        self.assertEqual(self.manager.list_invitations()[0]["status"], "expired")

    def test_invitation_api_requires_bearer_and_accepts_token(self) -> None:
        app = FastAPI()
        app.include_router(collaboration.router, prefix="/admin")
        with TestClient(app) as client:
            unauthorized = client.get("/admin/invitations")
            self.assertEqual(unauthorized.status_code, 401)
            created = client.post("/admin/invitations", headers={"Authorization": f"Bearer {self.session}"}, json={"display_name": "Dana", "role": "viewer"})
            self.assertEqual(created.status_code, 201, created.text)
            token = created.json()["invitation_token"]
            accepted = client.post("/admin/invitations/accept", json={"invitation_token": token})
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertEqual(accepted.json()["status"], "pending")


if __name__ == "__main__":
    unittest.main(verbosity=2)
