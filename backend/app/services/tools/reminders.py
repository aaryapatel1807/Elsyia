"""Persistent local reminders and a lightweight delivery worker."""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core import get_settings
from app.services.tools.base import Tool, ToolError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_due_at(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise ToolError("A due time is required in ISO-8601 format.")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError("Due time must be ISO-8601, for example 2026-08-20T09:30:00+05:30.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _db_path() -> Path:
    raw_path = Path(get_settings().REMINDER_DB_PATH)
    if not raw_path.is_absolute():
        raw_path = Path(__file__).parents[4] / raw_path
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    return raw_path


class ReminderStore:
    """Small SQLite store for user-owned local reminders."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else _db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    delivered_at TEXT
                )
                """
            )
            connection.commit()

    def create(self, title: str, due_at: datetime) -> dict[str, Any]:
        cleaned_title = " ".join(title.strip().split())
        if len(cleaned_title) < 2:
            raise ToolError("Reminder title must contain at least two characters.")
        if len(cleaned_title) > 300:
            raise ToolError("Reminder title is limited to 300 characters.")
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO reminders (title, due_at, created_at) VALUES (?, ?, ?)",
                (cleaned_title, due_at.isoformat(), _utc_now().isoformat()),
            )
            connection.commit()
            reminder_id = int(cursor.lastrowid)
        return self.get(reminder_id) or {}

    def get(self, reminder_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row) if row else None

    def list(self, include_completed: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM reminders"
        params: tuple[Any, ...] = ()
        if not include_completed:
            query += " WHERE status = 'pending'"
        query += " ORDER BY due_at ASC, id ASC LIMIT 100"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def cancel(self, reminder_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
                (reminder_id,),
            )
            connection.commit()
        if cursor.rowcount == 0:
            raise ToolError("Pending reminder not found.")
        return self.get(reminder_id) or {}

    def due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        current = (now or _utc_now()).astimezone(timezone.utc).isoformat()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM reminders WHERE status = 'pending' AND due_at <= ? ORDER BY due_at ASC",
                (current,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_delivered(self, reminder_id: int) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE reminders SET status = 'completed', delivered_at = ? WHERE id = ?",
                (_utc_now().isoformat(), reminder_id),
            )
            connection.commit()


async def deliver_reminder(reminder: dict[str, Any]) -> None:
    """Deliver a reminder through the Windows built-in session message utility."""
    if os.name != "nt":
        raise ToolError("Reminder notifications are currently supported on Windows only.")
    msg_path = shutil.which("msg.exe")
    if not msg_path:
        raise ToolError("Windows msg.exe is not available for local notifications.")
    message = f"Elysia reminder: {reminder['title']}"
    try:
        await asyncio.to_thread(
            subprocess.run,
            [msg_path, "*", "/TIME:60", message],
            check=True,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ToolError("Windows could not deliver the reminder notification.") from exc


async def reminder_worker(stop_event: asyncio.Event) -> None:
    """Deliver due reminders while the backend process is running."""
    settings = get_settings()
    store = ReminderStore()
    while not stop_event.is_set():
        for reminder in store.due():
            try:
                await deliver_reminder(reminder)
                store.mark_delivered(int(reminder["id"]))
            except ToolError:
                # Keep the reminder pending so a transient session/notification issue can recover.
                continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.REMINDER_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass


class CreateReminderTool(Tool):
    name = "create_reminder"
    description = "Create a persistent local Windows reminder after user confirmation."

    async def run(self, title: str, due_at: str) -> dict[str, Any]:
        reminder = ReminderStore().create(title, _parse_due_at(due_at))
        return {"reminder": reminder, "message": f"Reminder created for {reminder['due_at']}."}


class ListRemindersTool(Tool):
    name = "list_reminders"
    description = "List the user's pending local reminders without changing them."

    async def run(self, include_completed: bool = False) -> dict[str, Any]:
        reminders = ReminderStore().list(include_completed=include_completed)
        return {"reminders": reminders, "count": len(reminders)}


class CancelReminderTool(Tool):
    name = "cancel_reminder"
    description = "Cancel one pending local reminder after user confirmation."

    async def run(self, reminder_id: int) -> dict[str, Any]:
        if reminder_id <= 0:
            raise ToolError("Reminder ID must be positive.")
        return {"reminder": ReminderStore().cancel(reminder_id)}
