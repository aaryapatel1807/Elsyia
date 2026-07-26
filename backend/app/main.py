"""
Elysia Backend - Main Application Entry Point

This is the FastAPI application that powers Elysia's AI capabilities.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging

# Initialize settings
settings = get_settings()

# Setup logging
logger = setup_logging(settings.LOG_LEVEL, settings.LOG_FILE)


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
    
    yield
    
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


@app.get("/")
async def root() -> JSONResponse:
    """Root endpoint - health check."""
    return JSONResponse({
        "name": "Elysia",
        "version": "0.1.0",
        "status": "operational",
        "phase": 1,
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
