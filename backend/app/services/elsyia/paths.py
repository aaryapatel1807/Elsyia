"""Elsyia local data directory helpers.

All Elsyia-owned user data (contacts, notes, OAuth tokens) lives under one
directory, defaulting to ~/.elsyia so it survives repo checkouts and works
the same on every machine.
"""

from __future__ import annotations

from pathlib import Path

from app.core import get_settings


def elsyia_data_dir() -> Path:
    """Return the Elsyia data directory, creating it on first use."""
    raw = getattr(get_settings(), "ELSYIA_DATA_DIR", "~/.elsyia")
    path = Path(str(raw)).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def elsyia_file(name: str) -> Path:
    """Return a path inside the Elsyia data directory."""
    return elsyia_data_dir() / name
