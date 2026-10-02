# LLM Provider Support

Elysia now has working provider adapters for Ollama, OpenRouter, and Google Gemini behind the same `LLMProvider` interface.

| Provider | Adapter | Streaming | Model listing | Credentials required |
|---|---|---:|---:|---:|
| Ollama | Local REST client | Yes | Yes | No |
| OpenRouter | OpenAI-compatible REST client | Yes | Yes | `OPENROUTER_API_KEY` |
| Gemini | Google Generative Language REST client | Yes | Yes | `GOOGLE_API_KEY` |

OpenRouter and Gemini fail clearly when their API keys are empty rather than silently falling back or returning an opaque provider error. The active local default remains Ollama with `qwen2.5:1.5b` for speed.

Configure cloud providers in `.env`:

```env
DEFAULT_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=openai/gpt-4o-mini
```

or:

```env
DEFAULT_LLM_PROVIDER=gemini
GOOGLE_API_KEY=your-key
GEMINI_MODEL=gemini-2.0-flash
```

Provider adapter tests use in-memory HTTP transports and do not require live cloud credentials. A live cloud-provider benchmark requires the user to provide valid keys and should be run separately from the local latency benchmark.
