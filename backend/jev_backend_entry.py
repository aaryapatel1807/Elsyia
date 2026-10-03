"""Frozen-backend entry point for the Jev desktop app.

Used ONLY by PyInstaller (see jev-backend.spec). The Electron launcher
spawns the frozen binary and passes configuration through environment
variables — notably JEV_USER_DATA, PORT and SECRET_KEY.

Responsibilities:
  1. Make the bundled ``app`` package importable (sys._MEIPASS).
  2. Redirect every relative data path in Settings to an absolute path
     under JEV_USER_DATA, so SQLite databases, logs and downloaded models
     land in the user's app-data directory instead of the bundle
     (which is read-only / wiped on every launch in onefile mode).
  3. Start uvicorn via app.main:run().

This must run BEFORE ``app.main`` is imported, because app.main calls
get_settings() at module import time.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_sys_path() -> None:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:  # frozen by PyInstaller
        if meipass not in sys.path:
            sys.path.insert(0, meipass)
    else:  # dev: allow `python jev_backend_entry.py` straight from backend/
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)


_bootstrap_sys_path()

# Setting name -> path relative to JEV_USER_DATA.
# Mirrors the relative defaults in app.core.config.Settings.
_PATH_SETTINGS: dict[str, str] = {
    "LOG_FILE": "logs/elysia.log",
    "REMINDER_DB_PATH": "data/elysia_reminders.db",
    "MEMORY_DB_PATH": "data/elysia_memory.db",
    "AGENTS_DB_PATH": "data/elysia_agents.db",
    "PLAN_DB_PATH": "data/elysia_plans.db",
    "ENTERPRISE_DB_PATH": "data/elysia_enterprise.db",
    "SYNC_DB_PATH": "data/elysia_sync.db",
    "SYNC_RELAY_DB_PATH": "data/elysia_sync_relay.db",
    "CODE_INDEX_CACHE_PATH": "data/code_index.json",
    "SYNC_BACKUP_DIR": "data/sync_backups",
    "SYNC_RELAY_STORAGE_DIR": "data/sync_relay_packages",
    "INPUT_ATTACHMENT_DIR": "data/attachments",
    "BROWSER_DOWNLOAD_ROOT": "data/browser_downloads",
    "BROWSER_SCREENSHOT_ROOT": "data/browser_screenshots",
    "DESKTOP_TRASH_PATH": "data/elysia_trash",
    "PIPER_MODELS_DIR": "models/piper",
}


def _redirect_data_paths() -> None:
    root = os.environ.get("JEV_USER_DATA")
    if not root:
        return
    base = Path(root)
    for var, rel in _PATH_SETTINGS.items():
        if var not in os.environ:  # an explicit env var always wins
            os.environ[var] = str(base / rel)


_redirect_data_paths()


if __name__ == "__main__":
    from app.main import run

    run()
