# Changelog

All notable changes to Elysia will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## Phase 1 — Runtime Fixes

### Fixed
- **Backend build configuration**: Added `[tool.hatch.build.targets.wheel] packages = ["app"]` to pyproject.toml to resolve hatchling package discovery issue
- **Frontend ES module compatibility**: 
  - Updated Electron TypeScript config to compile to ES modules instead of CommonJS
  - Fixed `__dirname` usage in Electron main process by using `fileURLToPath(import.meta.url)` pattern
  - Added path alias resolution to Vite config for `@/*` imports
- **Dependencies installed**: Backend and frontend dependencies successfully installed

### Runtime Status
- ✅ **Backend**: Server starts successfully on http://127.0.0.1:8000
- ✅ **Basic API**: Health and status endpoints working
- ✅ **Chat API**: Available (requires Ollama for LLM functionality)
- ✅ **Voice API**: Endpoints available but require Piper voice model download
- ✅ **Frontend compilation**: TypeScript compiles successfully
- ✅ **Electron**: Application launches correctly

### Environment Setup Required
- **Ollama**: Not running (expected - local setup). Install from https://ollama.ai and run `ollama serve` + `ollama pull llama3.2`
- **Piper Voice Model**: Required download. Need `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json` in `backend/models/piper/`

---

## [Unreleased]

### Fixed
- **Voice loop THINKING → IDLE with no reply (2026-07-24)**
  - **Root cause**: `MediaRecorder.start()` without a `timeslice` argument doesn't fire `ondataavailable` until `stop()` is called, but `VoiceRecorder.stop()` immediately stops the stream and resolves before any data is collected. The recorded blob was empty/near-empty (0–3 KB, <0.2s), so Whisper transcribed empty string, and the frontend silently returned to idle.
  - **Fix**: Changed `this.mediaRecorder.start()` to `this.mediaRecorder.start(100)` in `frontend/src/lib/voice.ts` — this forces `ondataavailable` every 100ms while recording, ensuring chunks accumulate before `stop()` resolves.
  - **UX fix**: Added user-facing error message "Didn't catch that — try holding a little longer" in `useVoiceAssistant.ts` when transcription returns empty, so the red banner appears instead of a silent failure.
  - **Verification**: Recordings now 130–190 KB (3–4s), Whisper correctly transcribes ("Hello", "I'll play till I leave...").

- **Whisper model reloading on every request starving Ollama (2026-07-24)**
  - **Root cause**: `backend/app/api/v1/voice.py`'s `transcribe` endpoint called `create_stt_provider()` fresh per request. `WhisperSTTProvider.__init__` set `self._model = None`, so `_load_model()` loaded the entire Whisper model from scratch every time someone talked — logs showed "Loading Whisper model 'base'" before every transcription. This consumed time and memory, leaving insufficient resources for Ollama to load `llama3.2` when the subsequent chat request arrived, causing 120s timeouts.
  - **Fix**: Made STT/TTS providers long-lived singletons in `backend/app/services/voice/factory.py` via module-level cached instances (`get_stt_provider()` / `get_tts_provider()`). Same pattern applied to LLM provider in `backend/app/services/llm/factory.py` (`get_llm_provider()`) for consistency. Endpoints now use cached providers.
  - **Verification**: "Loading Whisper model" now appears **once** at startup, not per request. Chat responses complete normally (~1s) after transcription instead of timing out at 120s.

### Stage 3: Voice pipeline (Whisper STT + Piper TTS)

#### Added
- `backend/app/services/voice/` — STTProvider/TTSProvider interfaces, WhisperSTTProvider (faster-whisper), PiperTTSProvider, and a factory, following the same pattern as `services/llm/`
- `POST /api/v1/voice/transcribe` and `POST /api/v1/voice/speak` endpoints
- `PIPER_MODELS_DIR` setting — Piper needs downloaded `.onnx`/`.onnx.json` voice files placed here; they are not bundled
- Frontend: `lib/voice.ts` (mic capture + backend calls), `hooks/useVoiceAssistant.ts` (sequences listening → thinking → speaking), push-to-talk bound to holding Space in `App.tsx`, driving the orb's `assistantStatus`

#### Known gaps
- TTS synthesizes the full reply before playback starts (no incremental/streaming audio yet)
- Push-to-talk is keyboard-only; no global shortcut (works outside the focused window) yet — that needs an Electron global shortcut + native mic bridge, deferred
- No visual waveform/level meter while listening

### Merge: FRIDAY + ULTRON references into Elysia

#### Added
- Frontend scaffold (Electron + Vite + React + TypeScript + Tailwind) — did not exist before this merge
- Elysia presence orb (Three.js scene + camera-driven gesture control), ported from the ULTRON UI reference and restyled to match Elysia's premium/glass design language (no ULTRON branding or terminal styling carried over)
- `backend/app/services/tools/` — tool interface + system/web tools, ported from the FRIDAY reference project's MCP tool functions and reworked as plain async `Tool` subclasses. Not yet wired into the Phase 1 chat flow; scaffolded ahead of Phase 3 (Tool Calling) so the interface is stable when that phase starts

#### Removed
- Stray top-level FRIDAY demo files (`agent_friday.py`, `main.py`, `server.py`, `friday/` package) that had been sitting alongside the real backend — these were reference-project leftovers, not part of Elysia

### Phase 1 Development - In Progress

#### Added
- Initial project structure and architecture
- Comprehensive documentation (PRD, Roadmap, Architecture, etc.)
- Backend FastAPI foundation
- Frontend Electron + React scaffold
- Multi-provider LLM support (Ollama, OpenRouter, Gemini)
- Speech-to-text with Faster-Whisper
- Text-to-speech with Piper
- Push-to-talk voice interface
- Streaming AI responses
- Session conversation history
- Configuration system
- Logging infrastructure
- Beautiful dark theme UI

---

## [0.1.0] - TBD

### Phase 1: Foundation Release

First public alpha release of Elysia.

#### Added
- ✨ Voice assistant with push-to-talk
- 🎤 Speech recognition (Faster-Whisper)
- 🗣️ Text-to-speech (Piper, female voice)
- 💬 Streaming AI conversations
- 🧠 Multiple LLM provider support
- 📱 Modern Electron desktop app
- ⚙️ Configuration management
- 📝 Session conversation history
- 🎨 Beautiful dark theme UI
- 📚 Complete documentation

#### Technical
- FastAPI backend with async/await
- React + TypeScript frontend
- Pydantic models for type safety
- Clean architecture with SOLID principles
- Modular service layer
- Environment-based configuration
- Structured logging

---

## Future Releases

### [0.2.0] - Phase 2: Memory System

Planned features:
- Vector database integration
- Long-term conversation memory
- Semantic search over history
- User preference learning

### [0.3.0] - Phase 3: Vision Capabilities

Planned features:
- Screen capture and OCR
- Image understanding
- Document parsing
- Visual search

### [0.4.0] - Phase 4: Plugin Architecture

Planned features:
- Plugin SDK
- Marketplace
- Community plugins
- Sandboxed execution

### [0.5.0+] - Phases 5-12

See [ROADMAP.md](ROADMAP.md) for complete feature timeline.

---

## Version Naming Convention

- **Major.Minor.Patch** (e.g., 1.2.3)
- **Major:** Breaking changes, new phases
- **Minor:** New features, enhancements
- **Patch:** Bug fixes, minor improvements

**Alpha/Beta Tags:**
- `0.1.0-alpha.1` — Early development
- `0.1.0-beta.1` — Feature complete, testing
- `0.1.0-rc.1` — Release candidate
- `0.1.0` — Stable release

---

## Notes

- **Current Status:** Phase 1 development
- **Target Release:** Q1 2025
- **License:** MIT
