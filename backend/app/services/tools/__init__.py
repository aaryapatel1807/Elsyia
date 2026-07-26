"""
Tool Registry

Central list of tools available to Elysia. Ported and reworked from the
FRIDAY reference project (see system_tools.py / web_tools.py for
per-module notes on what changed during the port).

Importing this module does not activate tool-calling — it only makes
the tools available for a future Phase 3 tool-calling service to look
up. See app.services.tools.base for the phase-sequencing note.
"""

from app.services.tools.base import Tool, ToolError
from app.services.tools.system_tools import GetCurrentTimeTool, GetSystemInfoTool
from app.services.tools.web_tools import (
    FetchUrlTool,
    GetWorldFinanceNewsTool,
    GetWorldNewsTool,
    SearchWebTool,
)

AVAILABLE_TOOLS: list[Tool] = [
    GetCurrentTimeTool(),
    GetSystemInfoTool(),
    GetWorldNewsTool(),
    GetWorldFinanceNewsTool(),
    FetchUrlTool(),
    SearchWebTool(),
]

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in AVAILABLE_TOOLS}

__all__ = ["Tool", "ToolError", "AVAILABLE_TOOLS", "TOOLS_BY_NAME"]
