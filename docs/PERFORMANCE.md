# Elysia Performance Report

## Neural semantic memory

Elysia now uses the locally installed `nomic-embed-text` Ollama model for 768-dimensional neural embeddings. Embedding requests use a 750 ms budget and fall back to deterministic local vectors when the model is unavailable or cold. The embedding model is prewarmed in the background at startup and kept alive for 30 minutes.

The first direct embedding request after a cold model load measured approximately 31.3 seconds on the test machine. A warm request measured approximately 240 ms. Because cold embedding requests are bounded and fall back, a cold embedding model does not block the user-visible chat path; startup prewarming removes the usual cold penalty after sign-in.

## Text chat with memory injection

The memory-enabled local chat path remains below two seconds when the LLM and embedding models are warm. Earlier measurements were approximately 0.7–0.9 seconds for short requests; the end-to-end voice benchmark is slower because it includes CPU speech recognition and speech synthesis.

## End-to-end voice benchmark

The benchmark used a real WebM recording from `debug_audio`, Faster-Whisper tiny on CPU, local neural memory retrieval, Ollama `qwen2.5:1.5b`, and Piper `en_US-lessac-medium`. The second benchmark used the actual HTTP server after startup prewarming and the corrected project-root environment loading.

| Run | STT | Memory | LLM | TTS | Total |
|---|---:|---:|---:|---:|---:|
| Initial cold ASGI run | 8.2 s | 1.1 s | 2.0 s | 3.7 s | 15.0 s |
| Warm real HTTP run 1 | 1.6 s | 1.3 s | 2.5 s | 1.0 s | **6.4 s** |
| Warm real HTTP run 2 | 1.8 s | 1.1 s | 2.0 s | 1.0 s | **5.9 s** |

Startup prewarming reduced STT and TTS cold-start impact substantially. The complete voice path remains above two seconds because speech recognition, memory lookup, generation, and synthesis are sequential. The next major improvement would require overlapping stages or using a faster speech model/runtime; the current local CPU path is already materially faster after warmup.

## Provider support

OpenRouter and Gemini adapters now share the existing `LLMProvider` interface and support streaming, model listing, timeout handling, and clear missing-key errors. Adapter tests use in-memory HTTP transports. Live cloud latency was not measured because the active environment has blank cloud API keys.
