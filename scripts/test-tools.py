"""Phase 3 tool-calling integration checks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


class StubProvider:
    async def generate(self, messages, temperature=0.7, max_tokens=None):
        yield "Normal chat fallback."


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["ENABLE_MEMORY"] = "false"
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")

        import httpx

        from app.api.v1 import chat as chat_api
        from app.main import app
        from app.services.tools import registry
        from app.services.tools.intent import route_intent

        assert route_intent("what time is it").tool_name == "get_current_time"
        assert route_intent("open calculator").tool_name == "launch_application"
        assert route_intent("tell me a story") is None
        assert route_intent("search files for project notes").tool_name == "search_local_files"
        assert route_intent("draft a short thank-you note").tool_name == "draft_text"
        assert route_intent("list reminders").tool_name == "list_reminders"
        assert route_intent("remind me to stretch in 10 minutes").tool_name == "create_reminder"

        confirmation = await registry.execute("launch_application", {"application": "calculator"})
        assert confirmation.status == "confirmation_required"
        assert confirmation.confirmation_required is True

        direct = await registry.execute("get_current_time")
        assert direct.status == "completed"

        chat_api.create_llm_provider = lambda provider: StubProvider()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            tool_response = await client.post(
                "/api/v1/chat/",
                json={"message": "what time is it", "stream": False},
            )
            assert tool_response.status_code == 200, tool_response.text
            assert tool_response.json()["model"] == "local-tool-router"
            assert tool_response.json()["tool_result"]["status"] == "completed"

            pending = await client.post(
                "/api/v1/tools/launch_application",
                json={"arguments": {"application": "calculator"}},
            )
            assert pending.status_code == 200
            assert pending.json()["status"] == "confirmation_required"

            normal = await client.post(
                "/api/v1/chat/",
                json={"message": "Tell me a story", "stream": False},
            )
            assert normal.status_code == 200, normal.text
            assert normal.json()["response"] == "Normal chat fallback."

    print("tool integration checks passed")


if __name__ == "__main__":
    asyncio.run(main())
