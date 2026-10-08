"""
Elysia Backend - Main Application Entry Point

This is the FastAPI application that powers Elysia's AI capabilities.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.services.llm.factory import get_llm_provider
from app.services.memory.embeddings import prewarm_neural_embedding
from app.services.agents import agent_scheduler_worker
from app.services.input import attachment_processing_worker, get_attachment_store
from app.services.sync.relay import create_relay_router
from app.services.browser import browser_manager
from app.services.tools.reminders import reminder_worker
from app.services.voice.factory import get_stt_provider, get_tts_provider
from app.services.elsyia.wakeword import get_wakeword_service
from app.services.elsyia.mcp_client import get_mcp_manager

from app.core.logging import setup_logging

# Initialize settings
settings = get_settings()

# Setup logging
logger = setup_logging(settings.LOG_LEVEL, settings.LOG_FILE)


async def _prewarm_local_model() -> None:
    """Warm local models in the background without blocking application startup."""
    try:
        provider = get_llm_provider(settings.DEFAULT_LLM_PROVIDER)
        async for _ in provider.generate(
            [{"role": "user", "content": "Reply with one word: ready"}],
            temperature=0.0,
            max_tokens=1,
        ):
            pass
        logger.info("[STARTUP] Configured LLM warmup complete")
    except Exception as exc:
        # Startup must remain usable when a local server or cloud key is unavailable.
        logger.warning("[STARTUP] Configured LLM warmup skipped: %s", exc)

    if settings.MEMORY_EMBEDDING_PREWARM:
        try:
            warmed = await asyncio.to_thread(prewarm_neural_embedding)
            logger.info("[STARTUP] Neural embedding warmup %s", "complete" if warmed else "skipped")
        except Exception as exc:
            logger.warning("[STARTUP] Neural embedding warmup skipped: %s", exc)


async def _input_cleanup_worker(stop_event: asyncio.Event) -> None:
    """Expire copied attachments periodically without blocking request handling."""
    try:
        await asyncio.to_thread(get_attachment_store().clear_expired)
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=900)
            except asyncio.TimeoutError:
                await asyncio.to_thread(get_attachment_store().clear_expired)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("[INPUT] Attachment cleanup worker stopped: %s", exc)


async def _prewarm_voice_models() -> None:
    """Load STT and TTS models in the background before interactive use."""
    try:
        stt = get_stt_provider(settings.DEFAULT_STT_PROVIDER)
        if hasattr(stt, "warmup"):
            await stt.warmup()
        logger.info("[STARTUP] STT warmup complete")
    except Exception as exc:
        logger.warning("[STARTUP] STT warmup skipped: %s", exc)
    try:
        tts = get_tts_provider(settings.DEFAULT_TTS_PROVIDER)
        if hasattr(tts, "warmup"):
            await tts.warmup()
        logger.info("[STARTUP] TTS warmup complete")
    except Exception as exc:
        logger.warning("[STARTUP] TTS warmup skipped: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:

    """
    Application lifespan manager.
    
    Handles startup and shutdown tasks.
    """
    # Startup
    logger.info("[STARTUP] Elysia Backend starting...")
    logger.info(f"Environment: {'Development' if settings.DEBUG else 'Production'}")
    logger.info(f"Default LLM: {settings.DEFAULT_LLM_PROVIDER}/{settings.DEFAULT_LLM_MODEL}")
    warmup_tasks: list[asyncio.Task] = []
    reminder_stop = asyncio.Event()
    if settings.INPUT_ENABLED:
        warmup_tasks.append(asyncio.create_task(_input_cleanup_worker(reminder_stop)))
    if settings.INPUT_ENABLED and settings.INPUT_PROCESSING_ENABLED:
        warmup_tasks.append(asyncio.create_task(attachment_processing_worker(reminder_stop)))
    if settings.REMINDER_WORKER_ENABLED:
        warmup_tasks.append(asyncio.create_task(reminder_worker(reminder_stop)))
    if settings.AGENTS_WORKER_ENABLED:
        warmup_tasks.append(asyncio.create_task(agent_scheduler_worker(reminder_stop)))
    if settings.OLLAMA_PREWARM:
        warmup_tasks.append(asyncio.create_task(_prewarm_local_model()))
    if settings.VOICE_PREWARM:
        warmup_tasks.append(asyncio.create_task(_prewarm_voice_models()))
    try:
        get_wakeword_service().startup()
    except Exception as exc:  # noqa: BLE001 — wake word is optional
        logger.warning("[STARTUP] Wake-word listener skipped: %s", exc)
    try:
        get_mcp_manager().startup()
    except Exception as exc:  # noqa: BLE001 — MCP is optional
        logger.warning("[STARTUP] MCP client skipped: %s", exc)
    
    yield
    
    reminder_stop.set()
    await browser_manager.close_all()
    for warmup_task in warmup_tasks:
        if not warmup_task.done():
            warmup_task.cancel()
    get_wakeword_service().shutdown()
    try:
        await get_mcp_manager().aclose()
    except Exception as exc:  # noqa: BLE001 — best-effort session close
        logger.warning("[SHUTDOWN] MCP close skipped: %s", exc)

    # Shutdown

    logger.info("[SHUTDOWN] Elysia Backend shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Elysia API",
    description="The AI that understands, remembers, and acts",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,  # Disable docs in production
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS middleware for Electron frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")
if settings.SYNC_RELAY_ENABLED:
    app.include_router(create_relay_router(), prefix="/api/v1/sync-relay", tags=["sync-relay"])


@app.get("/")
async def root() -> JSONResponse:
    """Root endpoint - health check."""
    return JSONResponse({
        "name": "Elysia",
        "version": "0.1.0",
        "status": "operational",
        "phase": 12,

        "tagline": "The AI that understands, remembers, and acts"
    })


@app.get("/health")
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "version": "0.1.0"
    })


def run() -> None:
    """Run the application."""
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    run()
