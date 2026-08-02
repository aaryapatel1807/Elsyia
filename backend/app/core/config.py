"""
Configuration Management

Loads settings from environment variables and provides type-safe access.
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.
    
    Loads from environment variables with validation.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # === Server Settings ===
    HOST: str = Field(default="127.0.0.1", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # === LLM Providers ===
    DEFAULT_LLM_PROVIDER: Literal["ollama", "openrouter", "gemini"] = Field(
        default="ollama",
        description="Default LLM provider"
    )
    DEFAULT_LLM_MODEL: str = Field(
        default="llama3.2",
        description="Default LLM model"
    )
    
    # Ollama
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL"
    )
    
    # OpenRouter
    OPENROUTER_API_KEY: str = Field(default="", description="OpenRouter API key")
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API URL"
    )
    
    # Google Gemini
    GOOGLE_API_KEY: str = Field(default="", description="Google Gemini API key")
    
    # OpenAI (if using directly)
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    
    # === Speech Services ===
    DEFAULT_STT_PROVIDER: Literal["whisper"] = Field(
        default="whisper",
        description="Default STT provider"
    )
    DEFAULT_TTS_PROVIDER: Literal["piper"] = Field(
        default="piper",
        description="Default TTS provider"
    )
    
    # Whisper settings
    WHISPER_MODEL: Literal["tiny", "base", "small", "medium", "large"] = Field(
        default="tiny",
        description="Whisper model size"
    )
    WHISPER_DEVICE: Literal["cpu", "cuda"] = Field(
        default="cpu",
        description="Whisper device"
    )
    WHISPER_COMPUTE_TYPE: str = Field(
        default="int8",
        description="Whisper compute type"
    )
    
    # Piper settings
    PIPER_VOICE: str = Field(
        default="en_US-lessac-medium",
        description="Piper voice model"
    )
    PIPER_MODELS_DIR: str = Field(
        default="models/piper",
        description="Directory containing downloaded Piper .onnx voice models"
    )
    PIPER_SPEED: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Piper speech speed"
    )
    
    # === Logging ===
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    LOG_FILE: str = Field(
        default="logs/elysia.log",
        description="Log file path"
    )
    
    # === Security ===
    SECRET_KEY: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for encryption"
    )
    
    # === Performance ===
    MAX_CONCURRENT_REQUESTS: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum concurrent requests"
    )
    REQUEST_TIMEOUT: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Request timeout in seconds"
    )
    
    # === Feature Flags (Future Phases) ===
    ENABLE_MEMORY: bool = Field(default=False, description="Enable memory system (Phase 2)")
    ENABLE_VISION: bool = Field(default=False, description="Enable vision (Phase 3)")
    ENABLE_PLUGINS: bool = Field(default=False, description="Enable plugins (Phase 4)")


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Returns:
        Settings instance loaded from environment
    """
    return Settings()


# Convenience function for getting config
def get_config() -> Settings:
    """Alias for get_settings()."""
    return get_settings()
