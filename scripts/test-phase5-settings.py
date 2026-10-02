"""Regression checks for bounded direct Windows settings controls."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core import get_settings  # noqa: E402
from app.services.tools import registry  # noqa: E402
from app.services.tools.base import ToolError  # noqa: E402
from app.services.tools.desktop_controls import SetPowerPlanTool  # noqa: E402


class Phase5SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings().DESKTOP_SYSTEM_SETTINGS_ENABLED = False

    def test_registry_requires_confirmation(self) -> None:
        result = asyncio.run(registry.execute("set_power_plan", {"plan": "balanced"}))
        self.assertEqual(result.status, "confirmation_required")

    def test_disabled_setting_fails_closed(self) -> None:
        with patch("app.services.tools.desktop_automation.platform.system", return_value="Windows"):
            with self.assertRaises(ToolError):
                asyncio.run(SetPowerPlanTool().run("balanced"))

    def test_unknown_plan_is_rejected(self) -> None:
        get_settings().DESKTOP_SYSTEM_SETTINGS_ENABLED = True
        with patch("app.services.tools.desktop_automation.platform.system", return_value="Windows"):
            with self.assertRaises(ToolError):
                asyncio.run(SetPowerPlanTool().run("ultimate"))

    def test_allowlisted_plan_uses_fixed_powercfg_arguments(self) -> None:
        get_settings().DESKTOP_SYSTEM_SETTINGS_ENABLED = True
        completed = subprocess.CompletedProcess(["powercfg.exe"], 0, "", "")
        with patch("app.services.tools.desktop_automation.platform.system", return_value="Windows"):
            with patch("app.services.tools.desktop_controls._run_powercfg", return_value=completed) as runner:
                result = asyncio.run(SetPowerPlanTool().run("High Performance"))
        self.assertEqual(result["plan"], "high_performance")
        runner.assert_called_once_with(["/setactive", "SCHEME_MAX"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
