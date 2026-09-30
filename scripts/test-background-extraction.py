"""Verify chat response and background preference extraction behavior."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory


class StubProvider:
    async def generate(self, messages, temperature=0.7, max_tokens=None):
        yield "Acknowledged."


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["ENABLE_MEMORY"] = "true"
        os.environ["ENABLE_PREFERENCE_EXTRACTION"] = "true"
        os.environ["MEMORY_EMBEDDING_PROVIDER"] = "local"
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")

        import httpx

        from app.api.v1 import chat as chat_api
        from app.main import app
        from app.services.memory import get_memory_store

        chat_api.create_llm_provider = lambda provider: StubProvider()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.perf_counter()
            response = await client.post(
                "/api/v1/chat/",
                json={"message": "I prefer dark mode for the desktop app.", "stream": False},
            )
            response_ms = (time.perf_counter() - started) * 1000
            assert response.status_code == 200, response.text
            assert response.json()["response"] == "Acknowledged."
            await asyncio.sleep(0.25)

        memories = get_memory_store().list(include_pending=True)
        pending = [memory for memory in memories if "dark mode" in memory.content.lower()]
        assert pending and pending[0].approved is False
        assert get_memory_store().approve(pending[0].id) is True
        assert any("dark mode" in memory.content.lower() for memory in get_memory_store().list())
        print(f"background extraction checks passed response_ms={response_ms:.1f}")


if __name__ == "__main__":
    asyncio.run(main())
