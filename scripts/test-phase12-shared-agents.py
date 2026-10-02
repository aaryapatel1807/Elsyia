"""Regression checks for Phase 12 shared-agent grants."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.agents.manager import AgentManager  # noqa: E402
from app.services.enterprise.manager import EnterpriseManager, EnterpriseError  # noqa: E402
from app.services.enterprise.shared_agents import SharedAgentError, SharedAgentManager  # noqa: E402
import app.services.enterprise.shared_agents as shared_module  # noqa: E402


class Phase12SharedAgentTests(unittest.TestCase):
    def test_grant_authorize_and_revoke(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            settings = get_settings()
            settings.ENTERPRISE_DB_PATH = str(root / "enterprise.db")
            settings.ENTERPRISE_ADMIN_TOKEN = "local-admin-test"
            settings.ENTERPRISE_SESSION_SIGNING_KEY = "local-signing-test"
            enterprise = EnterpriseManager()
            agents = AgentManager(root / "agents.db")
            shared_module.agent_manager = agents
            agent = agents.create("Shared", "Prepare a safe local run")
            member = enterprise.add_member("Member", "member")
            session = enterprise.create_session("local-admin-test")["session_token"]
            grant_manager = SharedAgentManager(enterprise)
            grant = grant_manager.grant(session, agent.id, member.id, ["view", "prepare_run"])
            with patch.object(
                enterprise,
                "require_session",
                return_value={"principal_id": member.id, "role": "member"},
            ):
                self.assertTrue(grant_manager.authorize(session, agent.id, "view"))
            self.assertEqual(grant["capabilities"], ["prepare_run", "view"])
            with self.assertRaises(SharedAgentError):
                grant_manager.grant(session, agent.id, member.id, ["execute_shell"])
            grant_manager.revoke(session, grant["id"])
            with patch.object(
                enterprise,
                "require_session",
                return_value={"principal_id": member.id, "role": "member"},
            ):
                self.assertFalse(grant_manager.authorize(session, agent.id, "view"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
