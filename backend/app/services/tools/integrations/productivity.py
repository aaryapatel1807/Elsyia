"""Elsyia productivity integrations: timers and notes.

Timers reuse the existing local reminder store (a timer is a reminder due
in N minutes), so no new infrastructure is needed. Notes are a plain
markdown file at ~/.elsyia/notes.md — simple, durable, human-readable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.elsyia.paths import elsyia_file
from app.services.tools.base import Tool, ToolError
from app.services.tools.reminders import ReminderStore

_NOTES_FILE = "notes.md"


class SetTimerTool(Tool):
    name = "set_timer"
    description = (
        "Set a countdown timer for N minutes with an optional label. "
        "Implemented as a local reminder so it survives restarts."
    )

    async def run(self, minutes: int, label: str = "timer") -> dict[str, Any]:
        try:
            minutes_value = int(minutes)
        except (TypeError, ValueError) as exc:
            raise ToolError("The timer needs a whole number of minutes.") from exc
        if minutes_value < 1 or minutes_value > 1440:
            raise ToolError("Timers run from 1 minute to 24 hours.")
        due_at = datetime.now(timezone.utc) + timedelta(minutes=minutes_value)
        title = f"Timer: {(label or 'timer').strip()}"
        reminder = ReminderStore().create(title, due_at)
        return {
            "reminder": reminder,
            "message": f"Timer set for {minutes_value} minutes ({title}).",
        }


class TakeNoteTool(Tool):
    name = "take_note"
    description = "Save a quick note with a timestamp to Aarya's local notes file."

    async def run(self, text: str) -> dict[str, str]:
        text = (text or "").strip()
        if not text:
            raise ToolError("Tell me what to note down.")
        path = elsyia_file(_NOTES_FILE)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        entry = f"\n## {stamp}\n{text}\n"
        path.write_text(existing + entry, encoding="utf-8")
        return {"status": "noted", "timestamp": stamp}


class ReadNotesTool(Tool):
    name = "read_notes"
    description = "Read back Aarya's recent notes."

    async def run(self, max_chars: int = 2000) -> dict[str, str]:
        path = elsyia_file(_NOTES_FILE)
        if not path.exists():
            return {"notes": "", "message": "No notes yet."}
        content = path.read_text(encoding="utf-8")
        return {"notes": content[-max_chars:]}
