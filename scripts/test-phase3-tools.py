"""Regression checks for the remaining Phase 3 local tools."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


class FakeProvider:
    async def generate(self, messages, temperature=0.7, max_tokens=None):
        yield "This is a concise local result."


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        document = root / "project-notes.txt"
        document.write_text("Elysia Phase 3 should search local files safely.\n", encoding="utf-8")
        os.environ["TOOLS_FILE_ROOTS"] = str(root)
        os.environ["TOOLS_MAX_RESULTS"] = "5"
        os.environ["MEMORY_EMBEDDING_PROVIDER"] = "local"
        os.environ["REMINDER_DB_PATH"] = str(root / "reminders.db")
        os.environ["REMINDER_POLL_SECONDS"] = "5"

        from app.services.tools import registry
        from app.services.tools import draft_tools, file_tools
        from app.services.tools.file_tools import SearchLocalFilesTool, SummarizeLocalDocumentTool
        from app.services.tools.reminders import ReminderStore

        fake = FakeProvider()
        file_tools.create_llm_provider = lambda _provider: fake
        draft_tools.create_llm_provider = lambda _provider: fake

        name_result = await SearchLocalFilesTool().run("project-notes", mode="name")
        assert len(name_result["matches"]) == 1
        content_result = await SearchLocalFilesTool().run("search local files", mode="content")
        assert len(content_result["matches"]) == 1
        try:
            await SearchLocalFilesTool().run("project-notes", root=str(Path.home()))
        except Exception as exc:
            assert "configured local search roots" in str(exc)
        else:
            raise AssertionError("search escaped configured root")

        summary = await SummarizeLocalDocumentTool().run(str(document))
        assert summary["summary"] == "This is a concise local result."

        pending = await registry.execute(
            "create_reminder",
            {"title": "Review Phase 3", "due_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
            confirmed=False,
        )
        assert pending.status == "confirmation_required"
        created = await registry.execute(
            "create_reminder",
            {"title": "Review Phase 3", "due_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
            confirmed=True,
        )
        assert created.status == "completed"
        reminder_id = created.result["reminder"]["id"]
        listed = await registry.execute("list_reminders", {}, confirmed=False)
        assert listed.status == "completed" and listed.result["count"] == 1
        cancelled = await registry.execute("cancel_reminder", {"reminder_id": reminder_id}, confirmed=True)
        assert cancelled.status == "completed"

        due_store = ReminderStore(root / "due.db")
        due = due_store.create("Due now", datetime.now(timezone.utc) - timedelta(minutes=1))
        assert due_store.due() and due_store.due()[0]["id"] == due["id"]

        draft = await registry.execute(
            "draft_text",
            {"instruction": "Write a short thank-you note", "tone": "warm"},
            confirmed=False,
        )
        assert draft.status == "completed"
        assert draft.result["sent"] is False

    print("phase 3 tool checks passed")


if __name__ == "__main__":
    asyncio.run(main())
