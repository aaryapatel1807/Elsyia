"""
LLM Provider Factory

Creates LLM provider instances based on configuration.
Implements the Factory pattern for provider instantiation.
"""

from typing import Literal

from app.core import ConfigurationError, LLMError, get_settings, get_logger

from app.services.llm.base import LLMProvider
from app.services.llm.gemini import GeminiProvider
from app.services.llm.ollama import OllamaProvider
from app.services.llm.openrouter import OpenRouterProvider

logger = get_logger("llm.factory")

# Cached provider instances (singletons per provider)
_llm_providers: dict[str, LLMProvider] = {}


def get_llm_provider(
    provider: Literal["ollama", "openrouter", "gemini"] = "ollama"
) -> LLMProvider:
    """
    Get or create the LLM provider instance (cached per provider).

    Args:
        provider: Provider name ("ollama", "openrouter", or "gemini")

    Returns:
        Configured LLM provider instance

    Raises:
        ConfigurationError: If provider is unknown or misconfigured
    """
    global _llm_providers
    
    if provider not in _llm_providers:
        settings = get_settings()
        logger.info(f"Creating LLM provider: {provider}")

        if provider == "ollama":
            _llm_providers[provider] = OllamaProvider(
                base_url=settings.OLLAMA_BASE_URL,
                model=settings.DEFAULT_LLM_MODEL,
                keep_alive=settings.OLLAMA_KEEP_ALIVE,
                num_ctx=settings.OLLAMA_NUM_CTX,
                num_predict=settings.OLLAMA_NUM_PREDICT,
            )

        elif provider == "openrouter":
            try:
                _llm_providers[provider] = OpenRouterProvider(
                    api_key=settings.OPENROUTER_API_KEY,
                    base_url=settings.OPENROUTER_BASE_URL,
                    model=settings.OPENROUTER_MODEL,
                )
            except LLMError as exc:
                raise ConfigurationError(str(exc), details={"provider": provider}) from exc

        elif provider == "gemini":
            try:
                _llm_providers[provider] = GeminiProvider(
                    api_key=settings.GOOGLE_API_KEY,
                    base_url=settings.GEMINI_BASE_URL,
                    model=settings.GEMINI_MODEL,
                )
            except LLMError as exc:
                raise ConfigurationError(str(exc), details={"provider": provider}) from exc

        else:
            raise ConfigurationError(
                f"Unknown LLM provider: {provider}",
                details={"provider": provider, "available": ["ollama", "openrouter", "gemini"]}

            )
    
    return _llm_providers[provider]


# Deprecated alias for backward compatibility
def create_llm_provider(
    provider: Literal["ollama", "openrouter", "gemini"]
) -> LLMProvider:
    """Deprecated: use get_llm_provider() instead."""
    return get_llm_provider(provider)
