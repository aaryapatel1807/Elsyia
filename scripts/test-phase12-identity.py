"""Regression tests for Phase 12 identity and session readiness."""

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
from app.api.v1 import admin, identity  # noqa: E402
import app.services.enterprise.manager as enterprise_module  # noqa: E402
from app.services.enterprise import EnterpriseError, EnterpriseManager  # noqa: E402


class Phase12IdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = get_settings()
        self.settings.ENTERPRISE_ENABLED = True
        self.settings.ENTERPRISE_DB_PATH = str(root / "enterprise.db")
        self.settings.ENTERPRISE_WORKSPACE_ID = "identity-workspace"
        self.settings.ENTERPRISE_WORKSPACE_NAME = "Identity Workspace"
        self.settings.ENTERPRISE_ADMIN_TOKEN = "bootstrap-admin-token"
        self.settings.ENTERPRISE_SESSION_SIGNING_KEY = "local-session-signing-key-for-tests"
        self.settings.ENTERPRISE_SESSION_TTL_MINUTES = 60
        self.settings.ENTERPRISE_SSO_ENABLED = False
        self.settings.ENTERPRISE_SSO_ISSUER = ""
        self.settings.ENTERPRISE_SSO_CLIENT_ID = ""
        self.settings.ENTERPRISE_SSO_REDIRECT_URI = ""
        self.settings.ENTERPRISE_MFA_READINESS_ENABLED = True
        self.manager = EnterpriseManager()
        enterprise_module._manager = self.manager

    def tearDown(self) -> None:
        enterprise_module._manager = None
        self.temp.cleanup()

    def test_session_is_signed_and_hashed_at_rest(self) -> None:
        value = self.manager.create_session("bootstrap-admin-token")
        self.assertTrue(value["session_token"])
        self.assertEqual(self.manager.require_session(value["session_token"])["role"], "owner")
        connection = sqlite3.connect(self.settings.ENTERPRISE_DB_PATH)
        try:
            row = connection.execute("SELECT token_hash FROM sessions WHERE id = ?", (value["session_id"],)).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(row)
        self.assertNotIn(value["session_token"], row[0])
        tampered = value["session_token"][:-1] + ("0" if value["session_token"][-1] != "0" else "1")
        with self.assertRaises(EnterpriseError):
            self.manager.require_session(tampered)

    def test_revocation_and_mfa_readiness(self) -> None:
        value = self.manager.create_session("bootstrap-admin-token")
        enrollment = self.manager.enroll_mfa(value["session_token"])
        self.assertEqual(enrollment["status"], "pending_provider_setup")
        self.manager.revoke_session(value["session_token"])
        with self.assertRaises(EnterpriseError):
            self.manager.require_session(value["session_token"])

    def test_identity_and_admin_api_accept_bearer_session(self) -> None:
        app = FastAPI()
        app.include_router(identity.router, prefix="/admin/auth")
        app.include_router(admin.router, prefix="/admin")
        with TestClient(app) as client:
            created = client.post("/admin/auth/session", json={"admin_token": "bootstrap-admin-token"})
            self.assertEqual(created.status_code, 201, created.text)
            token = created.json()["session_token"]
            me = client.get("/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me.status_code, 200, me.text)
            status_response = client.get("/admin/status", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(status_response.status_code, 200, status_response.text)
            sso = client.post("/admin/auth/sso/start")
            self.assertEqual(sso.status_code, 200)
            self.assertFalse(sso.json()["enabled"])
            logout = client.post("/admin/auth/logout", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(logout.status_code, 204)
            after = client.get("/admin/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(after.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
