"""
Base LLM Provider Interface

Abstract base class defining the interface for all LLM providers.
Follows the Strategy pattern for easy provider swapping.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All LLM providers must implement this interface.
    """
    
    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate response from LLM.
        
        Args:
            messages: List of message dictionaries containing 'role' and 'content'
            temperature: Generation temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            
        Yields:
            Response tokens as they're generated
            
        Raises:
            LLMError: If generation fails
        """
        pass
    
    @abstractmethod
    async def get_available_models(self) -> list[str]:
        """
        Get list of available models for this provider.
        
        Returns:
            List of model names
        """
        pass
    
    async def cleanup(self) -> None:
        """
        Cleanup resources (optional).
        
        Override if provider needs cleanup (e.g., closing connections).
        """
        pass
