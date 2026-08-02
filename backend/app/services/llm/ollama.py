"""
Ollama LLM Provider

Implements LLM provider for local Ollama models.
"""

import json
from typing import AsyncGenerator, Optional

import httpx

from app.core import LLMError, get_logger
from app.services.llm.base import LLMProvider

logger = get_logger("llm.ollama")


class OllamaProvider(LLMProvider):
    """Ollama provider implementation for local LLM inference."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2"):
        """
        Initialize Ollama provider.
        
        Args:
            base_url: Ollama server URL
            model: Default model to use
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=300.0)  # 5-minute timeout for slow local cold starts
        logger.info(f"Ollama provider initialized: {base_url} (model: {model})")
    
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate response from Ollama.
        
        Args:
            messages: List of conversation messages
            temperature: Generation temperature
            max_tokens: Max tokens (not used by Ollama)
            
        Yields:
            Response tokens
            
        Raises:
            LLMError: If Ollama request fails
        """
        try:
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "keep_alive": "30m",
                "options": {
                    "temperature": temperature,
                    "num_predict": 300,   # cap at ~200 words for fast, sharp answers
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                }
            }
            
            logger.debug(f"Sending request to Ollama: {url}")
            
            async with self.client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"Ollama returned {response.status_code}: {error_text}")
                    raise LLMError(
                        f"Ollama returned status {response.status_code}",
                        provider="ollama",
                        details={"status_code": response.status_code, "error": error_text.decode()}
                    )
                
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                            
                            # Check if done
                            if data.get("done", False):
                                break
                        
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse Ollama response line: {line[:100]}")
                            continue
        
        except httpx.TimeoutException:
            logger.error("Ollama request timed out")
            raise LLMError("Request timed out - Ollama may be overloaded", provider="ollama")
        
        except httpx.ConnectError:
            logger.error(f"Failed to connect to Ollama at {self.base_url}")
            raise LLMError(
                f"Cannot connect to Ollama at {self.base_url}. Is Ollama running?",
                provider="ollama",
                details={"base_url": self.base_url}
            )
        
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise LLMError(f"Generation failed: {str(e)}", provider="ollama")
    
    async def get_available_models(self) -> list[str]:
        """
        Get list of models available in Ollama.
        
        Returns:
            List of model names
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [model["name"] for model in data.get("models", [])]
            logger.info(f"Available Ollama models: {models}")
            return models
        
        except Exception as e:
            logger.error(f"Failed to get Ollama models: {e}")
            return []
    
    async def cleanup(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
        logger.debug("Ollama provider cleaned up")
