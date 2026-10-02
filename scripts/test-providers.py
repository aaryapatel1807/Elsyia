"""Provider adapter tests using httpx in-memory transports."""

from __future__ import annotations

import asyncio
import httpx

from app.core import LLMError
from app.services.llm.gemini import GeminiProvider
from app.services.llm.openrouter import OpenRouterProvider


async def main() -> None:
    try:
        OpenRouterProvider(api_key="")
    except LLMError:
        pass
    else:
        raise AssertionError("OpenRouter accepted a missing key")

    try:
        GeminiProvider(api_key="")
    except LLMError:
        pass
    else:
        raise AssertionError("Gemini accepted a missing key")

    def openrouter_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        body = b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    openrouter = OpenRouterProvider(api_key="test-key")
    await openrouter.client.aclose()
    openrouter.client = httpx.AsyncClient(transport=httpx.MockTransport(openrouter_handler))
    output = ""
    async for token in openrouter.generate([{"role": "user", "content": "Hi"}]):
        output += token
    assert output == "Hello"
    await openrouter.cleanup()

    def gemini_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":streamGenerateContent")
        body = b'data: {"candidates":[{"content":{"parts":[{"text":"Hi"}]}}]}\n\n'
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    gemini = GeminiProvider(api_key="test-key")
    await gemini.client.aclose()
    gemini.client = httpx.AsyncClient(transport=httpx.MockTransport(gemini_handler))
    output = ""
    async for token in gemini.generate([{"role": "user", "content": "Hi"}]):
        output += token
    assert output == "Hi"
    await gemini.cleanup()

    print("provider adapter checks passed")


if __name__ == "__main__":
    asyncio.run(main())
