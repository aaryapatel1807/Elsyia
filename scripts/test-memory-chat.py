"""Verify that relevant memory is injected into chat context."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


class StubProvider:
    """Minimal streaming provider used to inspect the assembled prompt."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def generate(self, messages, temperature=0.7, max_tokens=None):
        self.messages = messages
        yield "Memory-aware response."


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")
        os.environ["ENABLE_MEMORY"] = "true"

        from httpx import ASGITransport, AsyncClient

        from app.api.v1 import chat as chat_api
        from app.main import app
        from app.services.memory import get_memory_store

        store = get_memory_store()
        store.save("Aarya prefers concise spoken answers.", category="preference")
        stub = StubProvider()
        chat_api.create_llm_provider = lambda provider: stub

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/",
                json={"message": "What spoken answers do you prefer?", "stream": False},
            )

        assert response.status_code == 200, response.text
        context = "\n".join(message["content"] for message in stub.messages)
        assert "Aarya prefers concise spoken answers." in context
        assert response.json()["response"] == "Memory-aware response."

    print("memory chat integration checks passed")


if __name__ == "__main__":
    asyncio.run(main())
