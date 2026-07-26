"""
LLM Provider Factory

Creates LLM provider instances based on configuration.
Implements the Factory pattern for provider instantiation.
"""

from typing import Literal

from app.core import ConfigurationError, get_settings, get_logger
from app.services.llm.base import LLMProvider
from app.services.llm.ollama import OllamaProvider

logger = get_logger("llm.factory")

# Cached provider instance (singleton per process)
_llm_provider: LLMProvider | None = None


def get_llm_provider(
    provider: Literal["ollama", "openrouter", "gemini"] = "ollama"
) -> LLMProvider:
    """
    Get or create the LLM provider instance (cached).

    Args:
        provider: Provider name ("ollama", "openrouter", or "gemini")

    Returns:
        Configured LLM provider instance

    Raises:
        ConfigurationError: If provider is unknown or misconfigured
    """
    global _llm_provider
    if _llm_provider is None:
        settings = get_settings()

        logger.info(f"Creating LLM provider: {provider}")

        if provider == "ollama":
            _llm_provider = OllamaProvider(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.DEFAULT_LLM_MODEL
            )

        elif provider == "openrouter":
            # TODO: Implement OpenRouter provider
            raise ConfigurationError(
                "OpenRouter provider not yet implemented. Coming soon!",
                details={"provider": provider}
            )

        elif provider == "gemini":
            # TODO: Implement Gemini provider
            raise ConfigurationError(
                "Gemini provider not yet implemented. Coming soon!",
                details={"provider": provider}
            )

        else:
            raise ConfigurationError(
                f"Unknown LLM provider: {provider}",
                details={"provider": provider, "available": ["ollama"]}
            )
    return _llm_provider


# Deprecated alias for backward compatibility
def create_llm_provider(
    provider: Literal["ollama", "openrouter", "gemini"]
) -> LLMProvider:
    """Deprecated: use get_llm_provider() instead."""
    return get_llm_provider(provider)
