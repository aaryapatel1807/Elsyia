# Changelog

All notable changes to Elysia will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## Overnight batch — 2026-10-08 (unreleased)

Non-visual, additive backend work (UI freeze honored). All commits local.

### Added
- **Morning briefing** (`morning_briefing` tool): composes today's calendar events,
  current weather (wttr.in, keyless), and pending reminders into one spoken
  summary. Each source is best-effort — the briefing never dies on one failure.
- **`search_web` is now real**: keyless metasearch via `ddgs` (MIT) with a
  backend fallback chain (bing → brave → duckduckgo → mojeek → google) — no API
  key needed. New intent patterns: "search the web for X", "google X", "look up X".
- **Article extraction**: `fetch_url` now returns readable article text via
  `trafilatura` (Apache-2.0), with raw-text fallback.
- **Stage-2 intent routing**: command-like utterances that beat the regex + fuzzy
  matchers get one local-LLM classification (temperature 0), validated against
  the real tool registry. LLM proposes, deterministic systems dispose.
- **`ask_user` mid-plan input**: agent plans can ask Aarya a clarifying question
  mid-flow; the plan pauses (`awaiting_input`) and resumes via
  `POST /jev/agent/{id}/confirm` with `{"user_input": "..."}` — the answer
  threads into later steps via `{{steps.N.answer}}`.
- **Ambient tools**: `get_weather` (keyless), `get_system_stats` (psutil),
  `get_world_news` (keyless RSS).
- **Memory consolidation**: post-turn extract → reconcile (mem0-style
  ADD/UPDATE/DELETE/NOOP) → save as pending-review facts (`approved=False`),
  behind `JEV_MEMORY_CONSOLIDATE` (default on). Fire-and-forget.
- **Conversation compaction**: auto-summarized history with summary injection
  into the LLM context on overflow.
- **Agent robustness**: one strict-prompt retry on empty plans; one retry on
  transient step exceptions (not timeouts/confirmations).
- **Natural-language times**: "in 5 minutes", "tomorrow at 5pm", "next monday at
  9am" for timers, reminders, and calendar events.
- **Cross-platform notifications**: reminders deliver via `desktop-notifier`
  (MIT) native toasts; Windows `msg.exe` kept as fallback.

### Fixed
- `embeddings.py`: `httpx.InvalidURL` escaped the best-effort except clause
  (not a subclass of `httpx.HTTPError`/`ValueError` in this httpx version);
  broadened to `Exception`.
- `memory/store.py`: `search()` now persists recomputed embeddings instead of
  recomputing them on every search.

### Tests
- 158 passing (was 106): `test_timeparse`, `test_intent_natural`,
  `test_ambient_tools`, `test_consolidate`, `test_compaction`,
  `test_stage2_askuser`, `test_web_tools`, `test_reminder_delivery`.

---

## Follow-up batch — 2026-10-08 (unreleased)

Decided items from the overnight report, implemented in one pass.
Non-visual, additive backend work (UI freeze honored). All commits local.

### Added
- **Memory-review API**: the consolidation pipeline's pending queue is now
  reviewable — `GET /memory/pending` (oldest first), `POST
  /memory/pending/{id}/approve`, `POST /memory/pending/{id}/reject`
  (deletes). Built for later UI work; no UI added.
- **MemOS-style phase-2 memory schema**: `valid_from`/`valid_to` temporal
  validity columns plus `trust` (0..1) and `provenance` scores on every
  memory. Retrieval now excludes expired / not-yet-valid facts and weights
  scores by trust (`× (0.5 + 0.5·trust)`; trust=1.0 behaves exactly as
  before). Legacy databases migrate automatically with safe defaults.
  New endpoints: `PATCH /memory/{id}/validity`, `PATCH
  /memory/{id}/trust`; create/list/export responses carry the new fields.
- **Recurring calendar events via gcsa** (MIT): new
  `create_recurring_calendar_event` tool — `daily`, `weekly`,
  `weekdays` (Mon–Fri), `monthly`, `yearly`, optional `count`/`until` —
  built on gcsa's pythonic Event/Recurrence API over Jev's existing OAuth
  credentials. The raw-API one-off event tools are untouched. Natural
  language: "schedule breakfast every weekday at 8am" routes to it.
  Added to the confirmation-gated tool set (writes to Aarya's calendar).

### Tests
- 195 passing (was 158): new `test_memory_review` (11), `test_memory_temporal`
  (11), `test_calendar_recurrence` (15).

### Dependencies
- `gcsa>=2.7.0` (MIT; transitive: `tzlocal` MIT, `beautiful-date` MIT,
  `python-dateutil` dual Apache-2.0/BSD — all permissive, license-verified
  from wheel metadata before adding).

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
- **Piper voice missing files (2026-07-31)**
  - **Root cause**: Piper voice `.onnx` and `.onnx.json` models were missing from `backend/models/piper/`, causing TTS to fail with TTSError.
  - **Fix**: Downloaded the `en_US-lessac-medium.onnx` model and its JSON config file to the designated directory.

- **Model lazy-load race condition (2026-07-31)**
  - **Root cause**: `WhisperSTTProvider` and `PiperTTSProvider` lazy-loaded models by checking `if self._model is None`. Concurrent requests saw `None` and loaded the model multiple times simultaneously, causing resource contention and garbled output.
  - **Fix**: Added `asyncio.Lock()` to `_load_model()` and `_load_voice()` in both providers to serialize the loading step without bottlenecking subsequent transcription/synthesis calls.

- **Overlapping recordings & unbound recording length (2026-07-31)**
  - **Root cause**: Successive push-to-talk attempts could trigger new recordings before previous ones finished, and missed keyup events could leave the microphone recording indefinitely (generating 5MB+ files).
  - **Fix**: Added a state check in `startListening()` to abort if `status !== "idle"`. Added a 15-second hard timeout via `setTimeout` to automatically stop recordings.

- **Stuck Space key push-to-talk state (2026-07-31)**
  - **Root cause**: If the Electron window lost focus while Space was held down, the browser missed the `keyup` event. Additionally, default browser behavior for Space sometimes interfered with clean event delivery. The internal recording state could become desynced from the application state.
  - **Fix**: Added a `blur` event listener to force stop the recording on focus loss. Called `e.preventDefault()` on Space down. Refactored state checking to derive `isRecording` directly from the recorder's existence rather than a separate `isHolding` flag. Added `Escape` key handler with a `forceResetToIdle` function to manually force-reset to idle for robust recovery.


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
