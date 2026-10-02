"""Google Gemini LLM provider using the Generative Language REST API."""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

import httpx

from app.core import LLMError, get_logger
from app.services.llm.base import LLMProvider

logger = get_logger("llm.gemini")


class GeminiProvider(LLMProvider):
    """Stream Gemini responses through Google's REST API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        if not api_key.strip():
            raise LLMError("Google API key is not configured", provider="gemini")
        self.api_key = api_key
        self.model = model.removeprefix("models/")
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=5.0))

    @staticmethod
    def _to_gemini_request(messages: list[dict]) -> tuple[dict | None, list[dict]]:
        system_parts: list[dict[str, str]] = []
        contents: list[dict] = []
        for message in messages:
            role = message.get("role", "user")
            content = str(message.get("content", ""))
            if not content:
                continue
            if role == "system":
                system_parts.append({"text": content})
            else:
                contents.append(
                    {
                        "role": "model" if role == "assistant" else "user",
                        "parts": [{"text": content}],
                    }
                )
        system_instruction = {"parts": system_parts} if system_parts else None
        return system_instruction, contents

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        system_instruction, contents = self._to_gemini_request(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens or 512,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        url = (
            f"{self.base_url}/models/{self.model}:streamGenerateContent"
            f"?alt=sse&key={self.api_key}"
        )
        try:
            async with self.client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise LLMError(
                        f"Gemini returned status {response.status_code}",
                        provider="gemini",
                        details={"body": body[:1000]},
                    )
                async for line in response.aiter_lines():
                    data = line.strip()
                    if data.startswith("data:"):
                        data = data[5:].strip()
                    if not data:
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    parts = event.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    for part in parts:
                        if part.get("text"):
                            yield part["text"]
        except httpx.TimeoutException as exc:
            raise LLMError("Gemini request timed out", provider="gemini") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini request failed: {exc}", provider="gemini") from exc

    async def get_available_models(self) -> list[str]:
        """Return Gemini models that support content generation."""
        try:
            response = await self.client.get(
                f"{self.base_url}/models",
                params={"key": self.api_key},
            )
            response.raise_for_status()
            models: list[str] = []
            for item in response.json().get("models", []):
                methods = item.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    models.append(str(item.get("name", "")).removeprefix("models/"))
            return [model for model in models if model]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Could not list Gemini models: %s", exc)
            return []

    async def cleanup(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
