"""Phase 5 desktop automation safety checks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        os.environ["DESKTOP_SAFE_ROOTS"] = str(root)
        os.environ["DESKTOP_TRASH_PATH"] = str(root / "trash")
        os.environ["DESKTOP_INPUT_ENABLED"] = "false"
        os.environ["DESKTOP_MAX_FILE_BYTES"] = "10000"

        from app.services.tools import registry
        from app.services.tools.desktop_automation import (
            GetActiveWindowTool,
            ListWindowsTool,
            NetworkStatusTool,
            ReadDesktopFileTool,
        )
        from app.services.tools.intent import route_intent

        assert route_intent("list windows").tool_name == "list_windows"
        assert route_intent("what window is active").tool_name == "get_active_window"
        assert route_intent("network status").tool_name == "network_status"
        assert route_intent("read clipboard").tool_name == "read_clipboard"

        source = root / "notes.txt"
        content = "Phase 5 reversible desktop automation."

        blocked = await registry.execute(
            "write_desktop_file",
            {"path": str(source), "content": content},
            confirmed=False,
        )
        assert blocked.status == "confirmation_required"

        written = await registry.execute(
            "write_desktop_file",
            {"path": str(source), "content": content},
            confirmed=True,
        )
        assert written.status == "completed"

        read = await ReadDesktopFileTool().run(str(source))
        assert read["content"] == content

        escaped = await registry.execute(
            "read_desktop_file",
            {"path": str(Path.home() / "outside.txt")},
            confirmed=False,
        )
        assert escaped.status == "failed"
        assert "safe roots" in (escaped.error or "")

        deleted_pending = await registry.execute(
            "delete_desktop_file",
            {"path": str(source)},
            confirmed=False,
        )
        assert deleted_pending.status == "confirmation_required"

        deleted = await registry.execute(
            "delete_desktop_file",
            {"path": str(source)},
            confirmed=True,
        )
        assert deleted.status == "completed"
        token = deleted.result["restore_token"]
        assert not source.exists()

        restored = await registry.execute(
            "restore_desktop_file",
            {"restore_token": token},
            confirmed=False,
        )
        assert restored.status == "completed"
        assert source.read_text(encoding="utf-8") == content

        input_result = await registry.execute(
            "press_key",
            {"key": "enter"},
            confirmed=True,
        )
        assert input_result.status == "failed"
        assert "disabled" in (input_result.error or "")

        # Read-only Windows inspection tools are safe to invoke; skip only if the host is non-Windows.
        try:
            windows = await ListWindowsTool().run()
            active = await GetActiveWindowTool().run()
            network = await NetworkStatusTool().run()
            assert isinstance(windows["count"], int)
            assert "window" in active
            assert "available" in network
        except Exception as exc:
            if os.name == "nt":
                raise
            assert "Windows" in str(exc)

    print("phase 5 desktop safety checks passed")


if __name__ == "__main__":
    asyncio.run(main())
