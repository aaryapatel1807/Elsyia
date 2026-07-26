"""
Status API Endpoints

Health checks and system status.
"""

from fastapi import APIRouter

from app.core import get_settings

router = APIRouter()


@router.get("/")
async def get_status():
    """
    Get API status.
    
    Returns:
        Status information including version and phase
    """
    return {
        "status": "ok",
        "version": "0.1.0",
        "phase": 1,
        "name": "Elysia"
    }


@router.get("/providers")
async def get_providers():
    """
    Get available providers and their configuration.
    
    Returns:
        Available LLM, STT, and TTS providers
    """
    settings = get_settings()
    
    return {
        "llm": {
            "default": settings.DEFAULT_LLM_PROVIDER,
            "default_model": settings.DEFAULT_LLM_MODEL,
            "available": ["ollama"],  # Will expand as providers are implemented
        },
        "stt": {
            "default": settings.DEFAULT_STT_PROVIDER,
            "available": ["whisper"],
        },
        "tts": {
            "default": settings.DEFAULT_TTS_PROVIDER,
            "available": ["piper"],
        },
    }
