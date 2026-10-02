"""Jev local data directory helpers.

All Jev-owned user data (contacts, notes, OAuth tokens) lives under one
directory, defaulting to ~/.jev so it survives repo checkouts and works
the same on every machine.
"""

from __future__ import annotations

from pathlib import Path

from app.core import get_settings


def jev_data_dir() -> Path:
    """Return the Jev data directory, creating it on first use."""
    raw = getattr(get_settings(), "JEV_DATA_DIR", "~/.jev")
    path = Path(str(raw)).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def jev_file(name: str) -> Path:
    """Return a path inside the Jev data directory."""
    return jev_data_dir() / name
