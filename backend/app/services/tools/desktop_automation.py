"""Bounded Windows desktop automation tools for Phase 5."""

from __future__ import annotations

import asyncio
import base64
import ctypes
from ctypes import wintypes
import os
import platform
import shutil
import subprocess
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core import get_settings
from app.services.tools.base import Tool, ToolError


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise ToolError("This desktop action is currently supported on Windows only.")


def _project_root() -> Path:
    return Path(__file__).parents[4].resolve()


def _safe_roots() -> list[Path]:
    settings = get_settings()
    configured = [part.strip() for part in settings.DESKTOP_SAFE_ROOTS.split(",") if part.strip()]
    if not configured:
        home = Path.home()
        configured = [str(home / name) for name in ("Desktop", "Documents", "Downloads")]
        configured.append(str(_project_root() / "data"))
    roots: list[Path] = []
    for raw in configured:
        root = Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
        if root.exists() and root.is_dir() and root not in roots:
            roots.append(root)
    return roots


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_path(raw_path: str, *, must_exist: bool = False) -> Path:
    if not raw_path or len(raw_path) > 1024:
        raise ToolError("A valid local path is required.")
    candidate = Path(os.path.expandvars(os.path.expanduser(raw_path)))
    resolved = candidate.resolve(strict=False)
    roots = _safe_roots()
    if not any(_is_within(resolved, root) for root in roots):
        raise ToolError("That path is outside the configured desktop safe roots.")
    if candidate.exists() and candidate.is_symlink():
        raise ToolError("Symlinked paths are not permitted for desktop file operations.")
    if must_exist and not candidate.exists():
        raise ToolError("That path does not exist.")
    if candidate.exists() and not (candidate.is_file() or candidate.is_dir()):
        raise ToolError("That path is not a regular file or directory.")
    return resolved


class _ActionLimiter:
    def __init__(self) -> None:
        self._timestamps: deque[float] = deque()

    def check(self) -> None:
        now = time.monotonic()
        window = 60.0
        while self._timestamps and now - self._timestamps[0] >= window:
            self._timestamps.popleft()
        if len(self._timestamps) >= get_settings().DESKTOP_ACTIONS_PER_MINUTE:
            raise ToolError("Desktop action rate limit reached; wait before trying again.")
        self._timestamps.append(now)


_limiter = _ActionLimiter()


def _user32() -> Any:
    _require_windows()
    return ctypes.windll.user32


def _window_info(hwnd: int) -> dict[str, Any] | None:
    user32 = _user32()
    if not user32.IsWindowVisible(hwnd):
        return None
    title_buffer = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title_buffer, 512)
    title = title_buffer.value.strip()
    if not title:
        return None
    rect = wintypes.RECT()

    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        "hwnd": int(hwnd),
        "title": title,
        "x": int(rect.left),
        "y": int(rect.top),
        "width": max(0, int(rect.right - rect.left)),
        "height": max(0, int(rect.bottom - rect.top)),
    }


class ListWindowsTool(Tool):
    name = "list_windows"
    description = "List visible desktop windows and their bounds without changing them."

    async def run(self) -> dict[str, Any]:
        _limiter.check()

        def collect() -> list[dict[str, Any]]:
            windows: list[dict[str, Any]] = []
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def callback(hwnd: int, _lparam: int) -> bool:
                info = _window_info(hwnd)
                if info:
                    windows.append(info)
                return True

            _user32().EnumWindows(callback_type(callback), 0)
            return windows[:100]

        windows = await asyncio.to_thread(collect)
        return {"windows": windows, "count": len(windows)}


class GetActiveWindowTool(Tool):
    name = "get_active_window"
    description = "Return the currently active visible desktop window."

    async def run(self) -> dict[str, Any]:
        _limiter.check()
        info = await asyncio.to_thread(lambda: _window_info(_user32().GetForegroundWindow()))
        return {"window": info}


class FocusWindowTool(Tool):
    name = "focus_window"
    description = "Focus a visible desktop window by its window handle."

    async def run(self, hwnd: int) -> dict[str, Any]:
        _limiter.check()
        if hwnd <= 0:
            raise ToolError("Window handle must be positive.")

        def focus() -> None:
            user32 = _user32()
            if not user32.IsWindow(hwnd):
                raise ToolError("Window handle is no longer valid.")
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)

        await asyncio.to_thread(focus)
        return {"hwnd": hwnd, "status": "focused"}


class MoveResizeWindowTool(Tool):
    name = "move_resize_window"
    description = "Move and resize a desktop window; requires confirmation."

    async def run(self, hwnd: int, x: int, y: int, width: int, height: int) -> dict[str, Any]:
        _limiter.check()
        if hwnd <= 0 or width < 100 or height < 80 or width > 8000 or height > 8000:
            raise ToolError("Invalid window handle or safe window dimensions.")

        def move_resize() -> None:
            user32 = _user32()
            if not user32.IsWindow(hwnd) or not user32.MoveWindow(hwnd, x, y, width, height, True):
                raise ToolError("Could not move or resize that window.")

        await asyncio.to_thread(move_resize)
        return {"hwnd": hwnd, "x": x, "y": y, "width": width, "height": height, "status": "updated"}


class CloseWindowTool(Tool):
    name = "close_window"
    description = "Send a close request to a desktop window; requires confirmation."

    async def run(self, hwnd: int) -> dict[str, Any]:
        _limiter.check()
        if hwnd <= 0:
            raise ToolError("Window handle must be positive.")

        def close() -> None:
            user32 = _user32()
            if not user32.IsWindow(hwnd) or not user32.PostMessageW(hwnd, 0x0010, 0, 0):
                raise ToolError("Could not send a close request to that window.")

        await asyncio.to_thread(close)
        return {"hwnd": hwnd, "status": "close_requested"}


class ReadDesktopFileTool(Tool):
    name = "read_desktop_file"
    description = "Read a bounded UTF-8 text file inside the desktop safe roots."

    async def run(self, path: str) -> dict[str, Any]:
        _limiter.check()
        file_path = _safe_path(path, must_exist=True)
        settings = get_settings()
        if not file_path.is_file():
            raise ToolError("Only regular files can be read.")
        if file_path.stat().st_size > settings.DESKTOP_MAX_FILE_BYTES:
            raise ToolError("File exceeds the configured desktop read limit.")
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8", errors="replace")
        truncated = len(content) > settings.DESKTOP_MAX_FILE_BYTES
        return {"path": str(file_path), "content": content[: settings.DESKTOP_MAX_FILE_BYTES], "truncated": truncated}


class WriteDesktopFileTool(Tool):
    name = "write_desktop_file"
    description = "Write a bounded UTF-8 text file inside the desktop safe roots; requires confirmation."

    async def run(self, path: str, content: str) -> dict[str, Any]:
        _limiter.check()
        settings = get_settings()
        if len(content) > settings.DESKTOP_MAX_FILE_BYTES:
            raise ToolError("Content exceeds the configured desktop write limit.")
        file_path = _safe_path(path)
        if file_path.exists() and not file_path.is_file():
            raise ToolError("The destination is not a regular file.")
        if not file_path.parent.exists():
            raise ToolError("The destination folder does not exist.")
        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")
        return {"path": str(file_path), "characters": len(content), "status": "written"}


class MoveDesktopFileTool(Tool):
    name = "move_desktop_file"
    description = "Move a local file between configured safe roots; requires confirmation."

    async def run(self, source: str, destination: str) -> dict[str, Any]:
        _limiter.check()
        source_path = _safe_path(source, must_exist=True)
        destination_path = _safe_path(destination)
        if not source_path.is_file() or destination_path.exists():
            raise ToolError("Source must be a file and destination must not already exist.")
        await asyncio.to_thread(shutil.move, str(source_path), str(destination_path))
        return {"source": str(source_path), "destination": str(destination_path), "status": "moved"}


def _trash_manifest() -> tuple[Path, dict[str, Any]]:
    raw = Path(get_settings().DESKTOP_TRASH_PATH)
    trash_dir = (raw if raw.is_absolute() else _project_root() / raw).resolve()
    trash_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = trash_dir / "manifest.json"
    if not manifest_path.exists():
        return manifest_path, {}
    try:
        import json

        return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ToolError("Desktop trash metadata is unavailable.") from exc


def _write_trash_manifest(path: Path, manifest: dict[str, Any]) -> None:
    import json

    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


class DeleteDesktopFileTool(Tool):
    name = "delete_desktop_file"
    description = "Move a local file into Elysia's reversible trash; requires confirmation."

    async def run(self, path: str) -> dict[str, Any]:
        _limiter.check()
        source_path = _safe_path(path, must_exist=True)
        manifest_path, manifest = _trash_manifest()
        token = uuid.uuid4().hex
        trash_path = manifest_path.parent / token
        await asyncio.to_thread(shutil.move, str(source_path), str(trash_path))
        manifest[token] = {
            "original_path": str(source_path),
            "trash_path": str(trash_path),
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "status": "deleted",
        }
        await asyncio.to_thread(_write_trash_manifest, manifest_path, manifest)
        return {"restore_token": token, "original_path": str(source_path), "status": "moved_to_trash"}


class RestoreDesktopFileTool(Tool):
    name = "restore_desktop_file"
    description = "Restore a previously deleted local file from Elysia's reversible trash."

    async def run(self, restore_token: str) -> dict[str, Any]:
        _limiter.check()
        if not restore_token or len(restore_token) > 80:
            raise ToolError("A valid restore token is required.")
        manifest_path, manifest = _trash_manifest()
        entry = manifest.get(restore_token)
        if not entry or entry.get("status") != "deleted":
            raise ToolError("Restore token was not found or was already restored.")
        original_path = _safe_path(str(entry["original_path"]))
        trash_path = Path(str(entry["trash_path"])).resolve()
        if original_path.exists() or not trash_path.exists():
            raise ToolError("The original destination is unavailable for restoration.")
        await asyncio.to_thread(shutil.move, str(trash_path), str(original_path))
        entry["status"] = "restored"
        entry["restored_at"] = datetime.now(timezone.utc).isoformat()
        await asyncio.to_thread(_write_trash_manifest, manifest_path, manifest)
        return {"path": str(original_path), "status": "restored"}


class ReadClipboardTool(Tool):
    name = "read_clipboard"
    description = "Read the current Windows text clipboard contents."

    async def run(self) -> dict[str, Any]:
        _limiter.check()
        _require_windows()
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"]
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                timeout=get_settings().DESKTOP_ACTION_TIMEOUT_SECONDS,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError("Could not read the Windows clipboard.") from exc
        if completed.returncode != 0:
            raise ToolError("Windows did not return text clipboard content.")
        content = completed.stdout
        limit = get_settings().DESKTOP_CLIPBOARD_MAX_CHARS
        return {"content": content[:limit], "truncated": len(content) > limit}


class WriteClipboardTool(Tool):
    name = "write_clipboard"
    description = "Replace the Windows text clipboard contents; requires confirmation."

    async def run(self, content: str) -> dict[str, Any]:
        _limiter.check()
        _require_windows()
        if len(content) > get_settings().DESKTOP_CLIPBOARD_MAX_CHARS:
            raise ToolError("Clipboard content exceeds the configured limit.")
        encoded = base64.b64encode(content.encode("utf-16le")).decode("ascii")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded}')) | Set-Clipboard",
        ]
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                text=True,
                timeout=get_settings().DESKTOP_ACTION_TIMEOUT_SECONDS,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError("Could not write the Windows clipboard.") from exc
        if completed.returncode != 0:
            raise ToolError("Windows rejected the clipboard update.")
        return {"characters": len(content), "status": "written"}


class NetworkStatusTool(Tool):
    name = "network_status"
    description = "Read a bounded summary of the current Windows network configuration."

    async def run(self) -> dict[str, Any]:
        _limiter.check()
        _require_windows()
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                ["ipconfig"],
                capture_output=True,
                text=True,
                timeout=get_settings().DESKTOP_ACTION_TIMEOUT_SECONDS,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ToolError("Could not inspect Windows network status.") from exc
        lines = [" ".join(line.split()) for line in completed.stdout.splitlines() if line.strip()]
        return {"available": completed.returncode == 0, "summary": lines[:40]}


_KEYS = {
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}


def _input_ready() -> None:
    _require_windows()
    if not get_settings().DESKTOP_INPUT_ENABLED:
        raise ToolError("Input automation is disabled. Set DESKTOP_INPUT_ENABLED=true to opt in.")


class PressKeyTool(Tool):
    name = "press_key"
    description = "Press one allowlisted keyboard key; requires confirmation and explicit input opt-in."

    async def run(self, key: str) -> dict[str, str]:
        _limiter.check()
        _input_ready()
        normalized = key.strip().lower()
        virtual_key = _KEYS.get(normalized)
        if virtual_key is None:
            raise ToolError("That key is not on the safe key allowlist.")
        user32 = _user32()
        await asyncio.to_thread(user32.keybd_event, virtual_key, 0, 0, 0)
        await asyncio.to_thread(user32.keybd_event, virtual_key, 0, 2, 0)
        return {"key": normalized, "status": "pressed"}


class KeyboardTypeTool(Tool):
    name = "keyboard_type"
    description = "Type limited ASCII text into the active window; requires confirmation and input opt-in."

    async def run(self, text: str) -> dict[str, Any]:
        _limiter.check()
        _input_ready()
        if not text or len(text) > 500 or any(ord(char) > 127 for char in text):
            raise ToolError("Keyboard typing accepts 1-500 ASCII characters only.")
        user32 = _user32()
        for char in text:
            virtual_key = user32.VkKeyScanA(ord(char)) & 0xFF
            if virtual_key == 0xFF:
                raise ToolError(f"Unsupported keyboard character: {char!r}")
            await asyncio.to_thread(user32.keybd_event, virtual_key, 0, 0, 0)
            await asyncio.to_thread(user32.keybd_event, virtual_key, 0, 2, 0)
        return {"characters": len(text), "status": "typed"}


class MouseClickTool(Tool):
    name = "mouse_click"
    description = "Click at a screen coordinate; requires confirmation and explicit input opt-in."

    async def run(self, x: int, y: int, button: str = "left") -> dict[str, Any]:
        _limiter.check()
        _input_ready()
        if button not in {"left", "right"} or not (-10000 <= x <= 10000 and -10000 <= y <= 10000):
            raise ToolError("Invalid mouse button or screen coordinate.")
        user32 = _user32()
        down = 0x0002 if button == "left" else 0x0008
        up = 0x0004 if button == "left" else 0x0010
        await asyncio.to_thread(user32.SetCursorPos, x, y)
        await asyncio.to_thread(user32.mouse_event, down, 0, 0, 0, 0)
        await asyncio.to_thread(user32.mouse_event, up, 0, 0, 0, 0)
        return {"x": x, "y": y, "button": button, "status": "clicked"}
