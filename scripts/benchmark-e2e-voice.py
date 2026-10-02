"""Benchmark the full local voice path: STT -> memory -> LLM -> TTS."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path


async def run_once(client, audio_path: Path, store) -> dict[str, float | int | str]:
    timings: dict[str, float | int | str] = {}
    audio_bytes = audio_path.read_bytes()

    started = time.perf_counter()
    transcribe_response = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": (audio_path.name, audio_bytes, "audio/webm")},
        timeout=180.0,
    )
    timings["stt_ms"] = (time.perf_counter() - started) * 1000
    if transcribe_response.status_code != 200:
        raise RuntimeError(f"STT failed: {transcribe_response.status_code} {transcribe_response.text}")
    transcript = transcribe_response.json().get("text", "").strip()
    message = f"{transcript or 'What short voice replies should you give?'} Please keep the answer concise."
    timings["transcript"] = transcript

    started = time.perf_counter()
    retrieved = await asyncio.to_thread(store.search, message, "default", 3)
    timings["memory_ms"] = (time.perf_counter() - started) * 1000
    timings["retrieved_memories"] = len(retrieved)

    started = time.perf_counter()
    chat_response = await client.post(
        "/api/v1/chat/",
        json={"message": message, "stream": False},
        timeout=60.0,
    )
    timings["llm_ms"] = (time.perf_counter() - started) * 1000
    if chat_response.status_code != 200:
        raise RuntimeError(f"LLM failed: {chat_response.status_code} {chat_response.text}")
    answer = chat_response.json().get("response", "").strip()

    started = time.perf_counter()
    tts_response = await client.post(
        "/api/v1/voice/speak",
        json={"text": answer or "Ready."},
        timeout=60.0,
    )
    timings["tts_ms"] = (time.perf_counter() - started) * 1000
    if tts_response.status_code != 200:
        raise RuntimeError(f"TTS failed: {tts_response.status_code} {tts_response.text}")
    timings["tts_bytes"] = len(tts_response.content)
    timings["total_ms"] = sum(
        float(timings[name]) for name in ("stt_ms", "memory_ms", "llm_ms", "tts_ms")
    )
    return timings


async def main() -> None:
    project = Path(__file__).resolve().parents[1]
    audio_candidates = sorted((project / "debug_audio").glob("*.webm"))
    if not audio_candidates:
        raise FileNotFoundError("No debug_audio/*.webm fixture found")
    audio_path = audio_candidates[-1]

    # Do not remove this directory in-process: Python/Whisper/Piper may retain
    # file handles on Windows. The benchmark artifact can be deleted afterward.
    benchmark_dir = Path(tempfile.mkdtemp(prefix="elysia-e2e-"))
    os.environ["ENABLE_MEMORY"] = "true"
    os.environ["MEMORY_DB_PATH"] = str(benchmark_dir / "benchmark.db")
    os.environ["MEMORY_EMBEDDING_PROVIDER"] = "ollama"
    os.environ["MEMORY_EMBEDDING_MODEL"] = "nomic-embed-text"
    os.environ["PIPER_MODELS_DIR"] = str(project / "backend" / "models" / "piper")
    os.environ["LOG_FILE"] = str(benchmark_dir / "benchmark.log")

    import httpx

    from app.main import app
    from app.services.memory import get_memory_store

    store = get_memory_store()
    store.save("Aarya prefers concise spoken answers.", category="preference")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        cold = await run_once(client, audio_path, store)
        warm = await run_once(client, audio_path, store)

    print(f"audio_fixture={audio_path.name}")
    print(f"benchmark_dir={benchmark_dir}")
    for label, result in (("cold", cold), ("warm", warm)):
        print(f"[{label}]")
        for key, value in result.items():
            if isinstance(value, float):
                print(f"{key}={value:.1f}")
            else:
                print(f"{key}={value}")
        print(f"text_under_2s={float(result['memory_ms']) + float(result['llm_ms']) < 2000}")
        print(f"voice_total_under_5s={float(result['total_ms']) < 5000}")


if __name__ == "__main__":
    asyncio.run(main())
