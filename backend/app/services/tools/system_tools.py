"""
System Tools

Basic host-system introspection tools. Ported from the FRIDAY reference
project's friday/tools/system.py — logic kept, MCP (@mcp.tool) decorator
pattern replaced with plain Tool subclasses so these run inside Elysia's
own FastAPI service layer instead of a separate MCP server process.
"""

import datetime
import platform
from typing import Any

from app.services.tools.base import Tool


class GetCurrentTimeTool(Tool):
    """Returns the current date and time in ISO 8601 format."""

    name = "get_current_time"
    description = "Get the current date and time in ISO 8601 format."

    async def run(self, **kwargs: Any) -> str:
        return datetime.datetime.now().isoformat()


class GetSystemInfoTool(Tool):
    """Returns basic information about the host system."""

    name = "get_system_info"
    description = "Get basic information about the host operating system."

    async def run(self, **kwargs: Any) -> dict[str, str]:
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
        }
