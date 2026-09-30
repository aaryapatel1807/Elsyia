"""Measure the deterministic tool route latency."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["ENABLE_MEMORY"] = "false"
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "memory.db")
        import httpx
        from app.main import app

        transport = httpx.ASGITransport(app=app)
        timings: list[float] = []
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(5):
                started = time.perf_counter()
                response = await client.post(
                    "/api/v1/chat/",
                    json={"message": "what time is it", "stream": False},
                )
                timings.append((time.perf_counter() - started) * 1000)
                assert response.status_code == 200, response.text
                assert response.json()["model"] == "local-tool-router"

        timings.sort()
        print("tool_route_runs_ms=" + ",".join(f"{value:.2f}" for value in timings))
        print(f"tool_route_median_ms={timings[len(timings) // 2]:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
