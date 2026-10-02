"""Benchmark the real chat endpoint with local memory injection enabled."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory


async def main() -> None:
    with TemporaryDirectory() as temporary_dir:
        os.environ["ENABLE_MEMORY"] = "true"
        os.environ["MEMORY_DB_PATH"] = str(Path(temporary_dir) / "benchmark.db")

        import httpx

        from app.main import app
        from app.services.memory import get_memory_store

        get_memory_store().save(
            "Aarya prefers concise spoken answers.",
            category="preference",
        )

        transport = httpx.ASGITransport(app=app)
        timings: list[float] = []
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            request = {
                "message": "What spoken answers do you prefer? Reply in one short sentence.",
                "stream": False,
            }
            # Warm the provider and memory path before measuring.
            warmup = await client.post("/api/v1/chat/", json=request, timeout=30.0)
            if warmup.status_code != 200:
                raise RuntimeError(f"Warmup failed: {warmup.status_code} {warmup.text}")

            for _ in range(3):
                started = time.perf_counter()
                response = await client.post("/api/v1/chat/", json=request, timeout=30.0)
                elapsed_ms = (time.perf_counter() - started) * 1000
                if response.status_code != 200:
                    raise RuntimeError(f"Chat failed: {response.status_code} {response.text}")
                timings.append(elapsed_ms)

        timings.sort()
        median = timings[len(timings) // 2]
        print(f"memory_injection_enabled=true")
        print(f"warm_runs_ms={','.join(f'{value:.1f}' for value in timings)}")
        print(f"median_ms={median:.1f}")
        print(f"under_2s={median < 2000}")


if __name__ == "__main__":
    asyncio.run(main())
