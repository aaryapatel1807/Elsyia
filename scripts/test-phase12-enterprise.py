"""Regression tests for the Phase 12 local enterprise foundation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.api.v1 import admin  # noqa: E402
import app.services.enterprise.manager as enterprise_module  # noqa: E402
from app.services.enterprise import EnterpriseError, EnterpriseManager  # noqa: E402


class Phase12EnterpriseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.settings = get_settings()
        self.settings.ENTERPRISE_ENABLED = True
        self.settings.ENTERPRISE_DB_PATH = str(Path(self.temp.name) / "enterprise.db")
        self.settings.ENTERPRISE_WORKSPACE_ID = "test-workspace"
        self.settings.ENTERPRISE_WORKSPACE_NAME = "Test Workspace"
        self.settings.ENTERPRISE_ADMIN_TOKEN = "admin-secret"
        self.settings.ENTERPRISE_MAX_MEMBERS = 5
        self.manager = EnterpriseManager()
        enterprise_module._manager = self.manager

    def tearDown(self) -> None:
        enterprise_module._manager = None
        self.temp.cleanup()

    def test_default_workspace_owner_and_policies(self) -> None:
        status = self.manager.status()
        self.assertEqual(status["workspace"].name, "Test Workspace")
        self.assertEqual(status["member_count"], 1)
        self.assertFalse(self.manager.policy_enabled("allow_cloud_sync"))
        self.assertFalse(self.manager.policy_enabled("analytics_opt_in"))
        with self.assertRaises(EnterpriseError):
            self.manager.require_admin("wrong")
        self.manager.require_admin("admin-secret")

    def test_member_role_and_owner_protections(self) -> None:
        member = self.manager.add_member("Alice", "viewer")
        self.assertEqual(member.role, "viewer")
        updated = self.manager.update_member(member.id, role="member", status="disabled")
        self.assertEqual(updated.status, "disabled")
        self.manager.delete_member(member.id)
        owner = next(item for item in self.manager.list_members() if item.role == "owner")
        with self.assertRaises(EnterpriseError):
            self.manager.delete_member(owner.id)
        with self.assertRaises(EnterpriseError):
            self.manager.update_member(owner.id, status="disabled")

    def test_policy_update_enables_opt_in_analytics_only_explicitly(self) -> None:
        self.manager.record_analytics("chat.completed")
        self.assertFalse(self.manager.analytics()["enabled"])
        self.manager.set_policy("analytics_opt_in", True)
        self.manager.record_analytics("chat.completed")
        self.manager.record_analytics("chat.completed")
        analytics = self.manager.analytics()
        self.assertTrue(analytics["enabled"])
        self.assertEqual(analytics["events"][0]["count"], 2)
        audit = self.manager.audit_summary()
        self.assertTrue(any(item["action"] == "policy.update" for item in audit["recent"]))

    def test_admin_api_requires_token_and_manages_members(self) -> None:
        app = FastAPI()
        app.include_router(admin.router, prefix="/admin")
        with TestClient(app) as client:
            locked = client.get("/admin/status")
            self.assertEqual(locked.status_code, 401)
            status_response = client.get("/admin/status", headers={"X-Elysia-Admin-Token": "admin-secret"})
            self.assertEqual(status_response.status_code, 200, status_response.text)
            created = client.post(
                "/admin/members",
                headers={"X-Elysia-Admin-Token": "admin-secret"},
                json={"display_name": "Bob", "role": "member"},
            )
            self.assertEqual(created.status_code, 201, created.text)
            policies = client.get("/admin/policies", headers={"X-Elysia-Admin-Token": "admin-secret"})
            self.assertEqual(policies.status_code, 200)
            self.assertTrue(any(item["key"] == "allow_cloud_sync" and item["enabled"] is False for item in policies.json()["policies"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
