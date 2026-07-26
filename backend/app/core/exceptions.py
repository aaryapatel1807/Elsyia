"""
Custom Exceptions

Domain-specific exceptions for better error handling.
"""

from typing import Any, Dict, Optional


class ElysiaException(Exception):
    """Base exception for Elysia."""
    
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize exception.
        
        Args:
            message: Error message
            code: Error code
            details: Additional details
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ConfigurationError(ElysiaException):
    """Configuration error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "CONFIGURATION_ERROR", details)


class ProviderError(ElysiaException):
    """External provider error (LLM, STT, TTS)."""
    
    def __init__(self, message: str, provider: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "PROVIDER_ERROR", details)
        self.provider = provider


class LLMError(ProviderError):
    """LLM provider error."""
    
    def __init__(self, message: str, provider: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, provider, details)
        self.code = "LLM_ERROR"


class STTError(ProviderError):
    """Speech-to-text error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "whisper", details)
        self.code = "STT_ERROR"


class TTSError(ProviderError):
    """Text-to-speech error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "piper", details)
        self.code = "TTS_ERROR"


class ValidationError(ElysiaException):
    """Input validation error."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "VALIDATION_ERROR", details)


class NotFoundError(ElysiaException):
    """Resource not found."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "NOT_FOUND", details)


class RateLimitError(ElysiaException):
    """Rate limit exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "RATE_LIMIT_EXCEEDED", details)


class TimeoutError(ElysiaException):
    """Request timeout."""
    
    def __init__(self, message: str = "Request timed out", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, "TIMEOUT", details)
