"""Measure the real HTTP voice pipeline after backend startup prewarming."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx


async def run_once(client: httpx.AsyncClient, audio_path: Path) -> dict[str, float | int | str]:
    result: dict[str, float | int | str] = {}
    audio = audio_path.read_bytes()

    started = time.perf_counter()
    response = await client.post(
        "/voice/transcribe",
        files={"audio": (audio_path.name, audio, "audio/webm")},
        timeout=180,
    )
    result["stt_ms"] = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    transcript = response.json().get("text", "").strip()
    message = f"{transcript or 'Please answer briefly.'} Please answer in one short sentence."
    result["transcript"] = transcript

    started = time.perf_counter()
    memory_response = await client.get(
        "/memory/",
        params={"scope": "default", "query": message},
        timeout=60,
    )
    result["memory_ms"] = (time.perf_counter() - started) * 1000
    memory_response.raise_for_status()
    result["retrieved_memories"] = memory_response.json().get("count", 0)

    started = time.perf_counter()
    chat_response = await client.post(
        "/chat/",
        json={"message": message, "stream": False},
        timeout=60,
    )
    result["llm_ms"] = (time.perf_counter() - started) * 1000
    chat_response.raise_for_status()
    answer = chat_response.json().get("response", "").strip()

    started = time.perf_counter()
    tts_response = await client.post(
        "/voice/speak",
        json={"text": answer},
        timeout=60,
    )
    result["tts_ms"] = (time.perf_counter() - started) * 1000
    tts_response.raise_for_status()
    result["tts_bytes"] = len(tts_response.content)
    result["total_ms"] = sum(float(result[key]) for key in ("stt_ms", "memory_ms", "llm_ms", "tts_ms"))
    return result


async def main() -> None:
    project = Path(__file__).resolve().parents[1]
    audio_path = sorted((project / "debug_audio").glob("*.webm"))[-1]
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000/api/v1") as client:
        first = await run_once(client, audio_path)
        second = await run_once(client, audio_path)
    print(f"audio_fixture={audio_path.name}")
    for label, result in (("run1", first), ("run2", second)):
        print(f"[{label}]")
        for key, value in result.items():
            print(f"{key}={value:.1f}" if isinstance(value, float) else f"{key}={value}")
        print(f"voice_total_under_10s={float(result['total_ms']) < 10000}")


if __name__ == "__main__":
    asyncio.run(main())
