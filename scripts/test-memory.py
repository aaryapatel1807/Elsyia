"""Phase 2 memory integration checks."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")
        os.environ["ENABLE_MEMORY"] = "true"

        from httpx import ASGITransport, AsyncClient

        from app.main import app
        from app.services.memory.store import MemoryStore

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/memory/",
                json={
                    "content": "Aarya prefers concise spoken answers.",
                    "category": "preference",
                },
            )
            assert response.status_code == 201, response.text
            memory_id = response.json()["id"]

            response = await client.post(
                "/api/v1/memory/",
                json={
                    "content": "Aarya is building the Elysia desktop assistant.",
                    "category": "project",
                },
            )
            assert response.status_code == 201, response.text

            response = await client.get("/api/v1/memory/?query=Elysia%20desktop")
            assert response.status_code == 200, response.text
            assert response.json()["count"] == 1
            assert "Elysia" in response.json()["memories"][0]["content"]

            response = await client.get("/api/v1/memory/?scope=other")
            assert response.status_code == 200, response.text
            assert response.json()["count"] == 0

            reopened = MemoryStore(str(Path(temporary_dir) / "memory.db"))
            assert len(reopened.list()) == 2

            response = await client.delete(f"/api/v1/memory/{memory_id}")
            assert response.status_code == 200, response.text

            response = await client.delete("/api/v1/memory/?scope=default")
            assert response.status_code == 200, response.text
            assert response.json()["deleted"] == 1

    print("memory integration checks passed")


if __name__ == "__main__":
    asyncio.run(main())
