"""Exercise the Phase 2 memory management API through FastAPI."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["ENABLE_MEMORY"] = "true"
        os.environ["MEMORY_EMBEDDING_PROVIDER"] = "local"
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")
        os.environ["MEMORY_ENCRYPTION_KEY"] = ""

        import httpx
        from app.main import app
        from app.services.memory.preferences import persist_candidates, extract_candidates

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/v1/memory/",
                json={"content": "Aarya likes dark mode", "category": "preference"},
            )
            assert created.status_code == 201, created.text

            pending_candidate = extract_candidates("I prefer concise answers.")
            assert persist_candidates(pending_candidate) == 1
            listed = await client.get("/api/v1/memory/?include_pending=true")
            assert listed.status_code == 200
            pending = [memory for memory in listed.json()["memories"] if not memory["approved"]]
            assert len(pending) == 1

            approved = await client.post(f"/api/v1/memory/{pending[0]['id']}/approve")
            assert approved.status_code == 200
            stats = await client.get("/api/v1/memory/stats")
            assert stats.json()["pending"] == 0
            assert stats.json()["total"] == 2

            reindexed = await client.post("/api/v1/memory/reindex")
            assert reindexed.status_code == 200
            assert reindexed.json()["reindexed"] == 2

            exported = await client.get("/api/v1/memory/export")
            assert exported.status_code == 200
            assert exported.json()["count"] == 2

    print("memory API checks passed")


if __name__ == "__main__":
    asyncio.run(main())
