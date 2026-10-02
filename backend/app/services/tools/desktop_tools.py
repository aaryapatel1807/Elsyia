"""Safe desktop actions for the first Phase 3 tool set."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
from typing import Any

from app.services.tools.base import Tool, ToolError


_ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "code": "code.exe",
    "visual studio code": "code.exe",
}


class LaunchApplicationTool(Tool):
    """Launch one allowlisted desktop application."""

    name = "launch_application"
    description = (
        "Open an allowlisted desktop application such as Calculator, Notepad, "
        "File Explorer, or Visual Studio Code. Requires confirmation."
    )

    async def run(self, application: str, **kwargs: Any) -> dict[str, str]:
        """Launch a known executable without invoking a shell."""
        if platform.system() != "Windows":
            raise ToolError("Application launching is currently supported on Windows only.")
        normalized = " ".join(application.lower().split())
        executable = _ALLOWED_APPS.get(normalized)
        if executable is None:
            raise ToolError("That application is not on Elysia's safe launch allowlist.")
        resolved = shutil.which(executable)
        if resolved is None and executable not in {"notepad.exe", "calc.exe", "explorer.exe"}:
            raise ToolError(f"Could not find {application} on this computer.")
        command = resolved or executable
        try:
            await asyncio.to_thread(
                subprocess.Popen,
                [command],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except OSError as exc:
            raise ToolError(f"Could not launch {application}: {exc}") from exc
        return {"application": application, "status": "launched"}
