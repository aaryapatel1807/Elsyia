"""
API v1 Router

Combines all v1 endpoints into a single router.
"""

from fastapi import APIRouter

from app.api.v1 import chat, status, voice

# Create main API router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(status.router, prefix="/status", tags=["status"])
api_router.include_router(voice.router, prefix="/voice", tags=["voice"])
