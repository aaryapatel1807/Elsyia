# Elysia

**The AI that understands, remembers, and acts.**

![Version](https://img.shields.io/badge/version-0.1.0--alpha-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Phase](https://img.shields.io/badge/phase-1-orange)


## 🎯 Vision

Elysia is not a chatbot. It is an **AI Operating System** designed to be your intelligent companion — capable of understanding context, remembering conversations, seeing your screen, controlling your desktop, browsing the web, and assisting with code.

This is **Phase 1** — the foundation. A beautiful, voice-enabled desktop assistant with streaming AI conversations.

---

## ✨ Current Features (Phase 1)

- ✅ **Push-to-Talk** — Press and hold to speak
- ✅ **Speech Recognition** — Powered by Faster-Whisper
- ✅ **Streaming AI Responses** — Real-time conversation with LLM
- ✅ **Female Voice** — Natural TTS via Piper
- ✅ **Session History** — Maintains conversation context
- ✅ **Beautiful Desktop UI** — Modern, minimal, and elegant
- ✅ **Multi-Provider LLM Support** — Ollama, OpenRouter, Gemini
- ✅ **FastAPI Backend** — Professional REST API architecture

---

## 🎩 Jev — the assistant at the heart of Elysia

**Jev** (like "Jeeves") is Elysia's named AI butler: a real, working voice
assistant, not a demo. Press **Ctrl+Shift+J** anywhere and Jev appears —
hold to talk, release, and he thinks and speaks back.

### The voice loop

```
hotkey → mic capture → Whisper STT → intent routing → Ollama reasoning
       → action execution → Piper TTS spoken reply
```

Engineered for latency: faster-whisper `tiny` (int8, beam size 1), a snappy
local Ollama model with a small context window, deterministic intent routing
that skips the LLM entirely for commands, and sentence-chunked TTS so the
first sentence starts speaking as soon as it is ready. Every turn reports
per-stage timings (`/jev/status`, `timings_ms` on every response).

### Run it

```bash
# 1. Backend
cd backend
python -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
cp ../.env.example .env   # edit as needed
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Ollama (separate terminal) — any snappy local model works
ollama pull qwen2.5:1.5b
ollama serve

# 3. Frontend (separate terminal)
cd frontend
npm install
npm run dev            # web UI at http://localhost:5173
npm run electron       # full desktop app with the Ctrl+Shift+J hotkey
```

Health check: `GET http://127.0.0.1:8000/api/v1/jev/status` reports STT,
LLM, TTS, Gmail and Calendar state in one call.

### What Jev can do

| Say | Jev does |
|---|---|
| "play lo-fi beats on YouTube" | Opens the exact video (with free Data API key) or YouTube search |
| "pause" / "next song" | System media keys (Windows) |
| "message mom on WhatsApp saying I'll be late" | Opens the chat with text prefilled, ready to send |
| "open LinkedIn jobs" / "search LinkedIn for internships" | Opens the right LinkedIn page |
| "play jazz on Spotify" | Opens Spotify search; media keys control playback |
| "check my email" / "search my emails for invoice" | Gmail via the official API |
| "send email to a@b.com subject hi saying hello" | Sends via Gmail (asks first) |
| "what's on my calendar" / "schedule dentist at …" | Google Calendar via the official API |
| "set a timer for 10 minutes called pasta" | Local persistent timer |
| "take a note buy milk" / "read my notes" | Timestamped notes at `~/.jev/notes.md` |
| "what time is it" / "open calculator" / "remind me …" | The full existing Elysia tool suite |

Destructive or outward-facing actions (sending email, creating calendar
events, deleting files, pressing keys) keep a confirmation step — Jev has
full permission to act, and asks once before doing anything irreversible.

### Honest limits

- **WhatsApp:** there is no free official API for personal WhatsApp
  messaging or reading chats. Jev uses `wa.me` deep links — the chat opens
  with your text prefilled and you press send. No scrapers, no unofficial
  automation, nothing against WhatsApp's terms.
- **LinkedIn:** posting via API requires a LinkedIn partnership, which is
  not available. Jev opens feeds, jobs, search and profiles; it does not
  fake posting.
- **Spotify:** full Web API playback control needs per-user OAuth and
  Spotify Premium. Jev opens Spotify and drives playback with media keys;
  the Web API path is documented as a future step, not faked.
- **YouTube:** without a `YOUTUBE_API_KEY`, "play X" opens search results
  rather than the exact video. The key is free with 10,000 quota units/day.
- **Media keys** (pause/next/previous) work on Windows with
  `DESKTOP_INPUT_ENABLED=true`.
- **Gmail/Calendar** need a one-time OAuth setup (below). Until then Jev
  tells you exactly how to connect instead of failing silently.

### Connect Gmail / Calendar (one-time, about 5 minutes)

Jev uses Google's official OAuth2 desktop-app flow. **You create the OAuth
client yourself — nothing is created in your Google account by this repo.**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create
   a project (any name, e.g. "Jev").
2. **APIs & Services → Library:** enable **Gmail API** and
   **Google Calendar API**.
3. **APIs & Services → OAuth consent screen:** choose **External**, fill in
   the app name and your email, add yourself as a test user, and add the
   scopes `.../auth/gmail.readonly`, `.../auth/gmail.send`,
   `.../auth/calendar`.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → application type **Desktop app** → download the JSON.
5. Set `JEV_GOOGLE_CLIENT_JSON=/path/to/your/client_secret.json` in `.env`
   (or `JEV_GOOGLE_CLIENT_ID` / `JEV_GOOGLE_CLIENT_SECRET`).
6. Say **"Jev, connect Gmail"** — your browser opens Google's consent page;
   approve, and the token is stored locally at `~/.jev/`. Same for
   **"Jev, connect calendar"**.

Jev never touches your live mailbox during development — the test suite
mocks the Gmail API.

### Jev's local data

Everything Jev owns lives in `~/.jev/` (override with `JEV_DATA_DIR`):
`contacts.json` (WhatsApp name → number map),
`notes.md`, and per-service Google OAuth tokens. Plain files, human-readable,
yours to edit.

### Wake word — hands-free summoning

Jev can listen for a wake phrase and summon itself, "Hey Siri" style. The
listener is a tiny on-device keyword spotter (openWakeWord, local ONNX
inference): it idles on the microphone watching only for the phrase, then
plays a chime, opens the overlay, and starts the normal voice loop. When
your turn finishes, it goes back to sleep.

**It is off by default.** Turn it on with the **Wake word** checkbox in the
Jev overlay — the always-on microphone is your explicit choice. You can
also start the backend with `JEV_WAKE_ENABLED=true`; the checkbox state is
remembered in `~/.jev/wakeword.json`.

**Privacy:** no audio ever leaves your machine. The mic stream is scored
in 80 ms frames on-device and discarded immediately — nothing is recorded,
stored, or transmitted. While a turn runs, the listener pauses itself so
Jev's own reply can't wake it again.

**Out of the box** it listens for **"hey jarvis"** (openWakeWord's
community model, downloaded automatically on first use). To teach it
**"hey jev"** in your own voice:

1. Record ~50 short clips of yourself saying "hey jev" (vary distance and
   room), plus ~20 clips of background noise and silence.
2. Train a model with the openWakeWord training notebook
   ([Google Colab](https://colab.research.google.com/github/dscripka/openWakeWord/blob/main/notebooks/train_openwakeword.ipynb))
   and export the `.onnx` file.
3. Drop it into `~/.jev/wakeword/hey_jev.onnx` and set
   `JEV_WAKE_MODEL=~/.jev/wakeword/hey_jev.onnx` in `backend/.env`.
4. Restart the backend and flip the toggle — the overlay shows the active
   phrase. `JEV_WAKE_THRESHOLD` (default 0.5) trades false wakes against
   missed ones; raise it if Jev wakes up uninvited.

**Cost:** roughly 1–3% of one CPU core and ~50 MB RAM while listening; the
model file is about 1 MB.

**Troubleshooting:** if the toggle reports the listener unavailable,
`pip install openwakeword sounddevice` (on Linux you also need the
`libportaudio2` system package). The test suite covers the trigger wiring
with a faked mic and model — no audio hardware needed.

---

## 🚀 Tech Stack

### Frontend
- **React** + **TypeScript** — Type-safe UI components
- **Vite** — Lightning-fast build tool
- **Electron** — Cross-platform desktop framework
- **TailwindCSS** — Utility-first styling

### Backend
- **Python 3.11+** — Modern async/await patterns
- **FastAPI** — High-performance API framework
- **Pydantic** — Runtime type validation
- **Uvicorn** — ASGI server

### AI Stack
- **Faster-Whisper** — Local speech-to-text
- **Piper TTS** — High-quality voice synthesis
- **Ollama / OpenRouter / Gemini** — Flexible LLM providers

---

## 📁 Project Structure

```
elysia/
├── docs/                    # Comprehensive documentation
│   ├── README.md
│   ├── PRD.md              # Product Requirements Document
│   ├── ROADMAP.md          # 12-phase development plan
│   ├── ARCHITECTURE.md     # System design & patterns
│   ├── TECH_STACK.md       # Technology decisions
│   ├── FEATURES.md         # Feature specifications
│   ├── API_SPEC.md         # REST API documentation
│   ├── UI_GUIDELINES.md    # Design system
│   ├── PERSONALITY.md      # AI character definition
│   ├── CODING_STANDARDS.md # Development guidelines
│   ├── MODULES.md          # Module documentation
│   ├── SECURITY.md         # Security practices
│   └── CHANGELOG.md        # Version history
│
├── frontend/               # Electron + React application
│   ├── src/
│   │   ├── main/          # Electron main process
│   │   ├── renderer/      # React UI
│   │   └── preload/       # Electron bridge
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                # Python FastAPI server
│   ├── app/
│   │   ├── api/           # REST API routes
│   │   ├── core/          # Core business logic
│   │   ├── services/      # Service layer
│   │   ├── models/        # Data models
│   │   └── utils/         # Utilities
│   ├── main.py
│   └── pyproject.toml
│
├── configs/                # Configuration files
│   ├── settings.yaml      # Application settings
│   └── providers.yaml     # LLM provider configs
│
├── prompts/                # System prompts
│   └── elysia.txt         # Personality definition
│
├── memory/                 # Future: Vector storage (Phase 2)
├── plugins/                # Future: Plugin system (Phase 4)
├── assets/                 # Images, icons, sounds
├── scripts/                # Build & deployment scripts
├── tests/                  # Test suites
│
├── .env.example
├── .gitignore
├── README.md
└── LICENSE
```

---

## 🎨 Design Philosophy

Elysia's UI draws inspiration from:
- **Apple Intelligence** — Minimal, refined, ambient
- **Nothing OS** — Bold simplicity
- **Arc Browser** — Modern interaction patterns
- **Iron Man JARVIS/FRIDAY** — Futuristic HUD aesthetics

### Design Principles
- **Minimal** — Remove everything unnecessary
- **Elegant** — Beauty in simplicity
- **Ambient** — Feels like magic, not machinery
- **Fast** — Instant feedback, smooth animations
- **Dark** — Easy on the eyes, premium feel

---

## 🛠 Installation

> **Note:** Elysia is under active development. Jev (the voice assistant)
> is the working centrepiece — see the Jev section above.

### Prerequisites
- **Node.js** 18+
- **Python** 3.11+
- **Ollama** installed locally ([ollama.com](https://ollama.com)) with a
  snappy model pulled, e.g. `ollama pull qwen2.5:1.5b`
- No paid APIs, no cloud keys — everything runs local-first and free.

### Quick Start

```bash
# Clone repository
git clone https://github.com/aaryapatel1807/Elsyia.git
cd Elsyia

# Backend setup
cd backend
python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
cp ../.env.example .env   # optional: tune providers and keys

# Start the backend (leave running)
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend setup (separate terminal)
cd frontend
npm install
npm run dev               # web UI at http://localhost:5173

# Desktop app with the Ctrl+Shift+J global hotkey (separate terminal)
npm run electron:dev
```

### Verify the loop

```bash
# Backend health
curl http://127.0.0.1:8000/health

# Jev loop health: STT, LLM, TTS, Gmail/Calendar state
curl http://127.0.0.1:8000/api/v1/jev/status

# One text turn through Jev (no audio needed)
curl -X POST http://127.0.0.1:8000/api/v1/jev/ask \
  -H 'Content-Type: application/json' \
  -d '{"message":"what time is it"}'

# Run the test suite
cd backend && ./.venv/bin/python -m pytest tests/ -q
```

---

## 🗺 Roadmap

### ✅ Phase 1: Voice Assistant (Current)
Push-to-talk, STT, LLM streaming, TTS, conversation history

### Phase 2: Memory System
Long-term memory, context retrieval, user preferences

### Phase 3: Vision Capabilities
Screen understanding, OCR, image analysis

### Phase 4: Plugin Architecture
Extensible tool system, community plugins

### Phase 5: Desktop Automation
Window control, file operations, app launching

### Phase 6: Browser Automation
Web scraping, form filling, navigation

### Phase 7: Code Assistant
Repository analysis, code generation, refactoring

### Phase 8: Planning & Reasoning
Multi-step task execution, goal decomposition

### Phase 9: Autonomous Agents
Background task execution, proactive assistance

### Phase 10: Multi-Modal Input
Camera, clipboard, file drag-drop

### Phase 11: Cloud Sync
Cross-device memory, settings sync

### Phase 12: Enterprise Features
Team collaboration, admin controls, audit logs

See [ROADMAP.md](docs/ROADMAP.md) for details.

---

## 📖 Documentation

- **[Product Requirements](docs/PRD.md)** — What and why
- **[Architecture](docs/ARCHITECTURE.md)** — How it works
- **[API Specification](docs/API_SPEC.md)** — Endpoint documentation
- **[UI Guidelines](docs/UI_GUIDELINES.md)** — Design system
- **[Coding Standards](docs/CODING_STANDARDS.md)** — Development rules

---

## 🤝 Contributing

Contributions welcome! Please read our coding standards and submit PRs following our architecture patterns.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

---

## 🙏 Acknowledgments

- Inspired by Tony Stark's AI assistants (JARVIS, FRIDAY)
- Built with love for the AI community

---

**Status:** 🚧 Phase 1 Development — Alpha Release Coming Soon
