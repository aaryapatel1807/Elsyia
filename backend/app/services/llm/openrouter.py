"""OpenRouter LLM provider using the OpenAI-compatible chat API."""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

import httpx

from app.core import LLMError, get_logger
from app.services.llm.base import LLMProvider

logger = get_logger("llm.openrouter")


class OpenRouterProvider(LLMProvider):
    """Stream chat completions through OpenRouter."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "openai/gpt-4o-mini",
    ) -> None:
        if not api_key.strip():
            raise LLMError(
                "OpenRouter API key is not configured",
                provider="openrouter",
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=5.0))

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens or 512,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Elysia",
        }
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise LLMError(
                        f"OpenRouter returned status {response.status_code}",
                        provider="openrouter",
                        details={"body": body[:1000]},
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    content = event.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        yield content
        except httpx.TimeoutException as exc:
            raise LLMError("OpenRouter request timed out", provider="openrouter") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenRouter request failed: {exc}", provider="openrouter") from exc

    async def get_available_models(self) -> list[str]:
        """Return model IDs advertised by OpenRouter."""
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            return [item["id"] for item in response.json().get("data", []) if item.get("id")]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Could not list OpenRouter models: %s", exc)
            return []

    async def cleanup(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
