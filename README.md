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

### Dictation mode — say it, it types

Press **Ctrl+Shift+D** anywhere on your system and Jev starts recording —
press it again and your words get typed into whichever app was focused:
Gmail, Docs, Notion, a chat box, a terminal, anywhere. Speaking runs at
roughly 150 words per minute against ~40 for typing, so this is the
fastest way to get text out of your head.

Before anything is typed, the raw transcript goes through an **instant
cleanup** pass on your local Ollama model: filler words are stripped,
punctuation and obvious mishears are fixed, and self-corrections are
resolved to what you actually meant:

> say: *"um so, uh, meet at 2... no, 3pm"*
> get: *"Meet at 3pm."*

Your language is preserved — Hinglish stays Hinglish; nothing is
translated, and nothing is ever added.

**The flow:** hotkey → red recording dot in the overlay (Esc cancels) →
hotkey again → cleanup → a preview popup shows the cleaned text with
**Type it / Re-record / Cancel**. Set `JEV_DICTATION_CONFIRM=false` in
`backend/.env` to skip the preview and type immediately. The overlay
hides itself before typing so your keystrokes land in the right app, and
the wake-word listener pauses while you dictate so Jev can't hear itself.

Dictation is a separate, silent mode: it types text and never triggers
Jev's spoken reply loop.

**Privacy:** everything is on-device — faster-whisper for transcription,
Ollama for cleanup, pynput for typing. No audio leaves your machine and
nothing is stored after the turn.

**Windows setup:** allow microphone access for the app
(Settings → Privacy & security → Microphone), and make sure the backend
has `pynput` (`pip install pynput` — it is in the backend dependencies).
If typing reports unavailable, that is the missing piece.

**Customising:** the hotkey is `JEV_DICTATION_HOTKEY` in `backend/.env`
(read by the Electron shell at launch, so set it before starting the
app). The cleanup prompt lives in `prompts/dictation-cleanup.txt` — edit
it to change how aggressive the cleanup is.

---

### Jev's voice — pick the Jarvis voice

Jev speaks with Piper, a free neural text-to-speech engine that runs
entirely on your machine. Out of the box Jev uses **en_GB-alan-medium** —
a deep British male voice, chosen because it is the closest free Piper
voice to the Jarvis/butler archetype (and a natural fit for a butler
named Jev). If you prefer an American voice, `en_US-ryan-medium` is the
closest male alternative. Character is subjective, so listen and pick
your favourite — switching is instant and needs no restart.

**API** (no UI changes — this is all endpoints and config):

- `GET /jev/voice/list` — every known voice: which are downloaded, which
  can be fetched, and which one is active.
- `POST /jev/voice/preview` `{"voice_id": "...", "text": "..."}` — hear a
  sample line in that voice *without* changing the active one.
- `POST /jev/voice/download` `{"voice_id": "..."}` — fetch a voice from
  HuggingFace (streams progress). Explicit only: Jev never downloads
  voices on its own.
- `POST /jev/voice/select` `{"voice_id": "..."}` — make it Jev's voice.
  Takes effect immediately; the choice is remembered in
  `~/.jev/voice.json`.

Example:

```bash
curl -s localhost:8000/api/v1/jev/voice/list | python3 -m json.tool
curl -X POST localhost:8000/api/v1/jev/voice/download \
  -H 'Content-Type: application/json' -d '{"voice_id":"en_US-ryan-medium"}'
# then, after the download finishes:
curl -X POST localhost:8000/api/v1/jev/voice/select \
  -H 'Content-Type: application/json' -d '{"voice_id":"en_US-ryan-medium"}'
```

**Config:** `JEV_TTS_VOICE` in `backend/.env` sets the default voice;
a persisted choice from `/jev/voice/select` overrides it. The underlying
provider default is `PIPER_VOICE` (now `en_GB-alan-medium`); downloaded
voices live in `models/piper/`. The full catalogue of downloadable
voices is at <https://huggingface.co/rhasspy/piper-voices> — any voice id
in Piper's `lang_REGION-name-quality` shape can be fetched.

---

### Agent mode — say it and it's done

Open the Jev overlay and expand **▸ Agent mode**. Type one command that
needs several things to happen, and Jev plans and runs the whole chain:

> "grab my flight info from Gmail, put it on my calendar, and text Mom the details"

Behind that sentence: your local Ollama model breaks the command into an
ordered plan against Jev's real tool list (never invented tools), then
runs it step by step — search Gmail → read the flight email → create the
calendar event → open WhatsApp with the message prefilled. Outputs are
threaded forward, so the flight details found in step 2 become the
calendar event and the WhatsApp text. Each step narrates itself in the
overlay ("Finding your flight email… ✓"), and Jev speaks a summary at
the end.

A few more things it handles:

> "find the Q3 report in my email and send the summary to Priya on WhatsApp"
> "what's on my calendar today, and remind me about the dentist at 6pm"

**The rules it runs by:**

- **Fast path first.** A single simple action ("what time is it") never
  touches the planner — the deterministic router handles it instantly.
  The planner only engages for multi-step commands.
- **Reads are silent, outward actions ask.** Anything that acts on the
  outside world — sending an email, creating a calendar event — pauses
  the plan and waits for your tap (or "yes") before continuing. The rest
  of the plan resumes exactly where it stopped.
- **At most 5 steps** per plan (`JEV_AGENT_MAX_STEPS`), each with its own
  timeout (`JEV_AGENT_STEP_TIMEOUT_S`, 60 seconds default).
- **Failure is honest.** If step 2 of 4 fails, the plan stops, keeps the
  partial results, and tells you exactly what succeeded and where it got
  stuck. Nothing is silently skipped.

**Honest limits:** chaining is only as capable as the underlying
integrations. WhatsApp opens the chat with your message prefilled —
there is no free official API for personal WhatsApp, so you still tap
send yourself. LinkedIn opens deep links; it can't post. And the planner
is only as clever as your local model — if it can't break a command
down, it says so instead of guessing.

Developers: `POST /jev/agent` (add `stream: true` for live server-sent
step events), `POST /jev/agent/{plan_id}/confirm` to resume after a
confirmation pause, `GET /jev/agent/status` for health. The planner
prompt lives in `prompts/agent-planner.txt`.

---

### Screen-aware mode — circle anything, then just ask

Press **Ctrl+Shift+S**. Your screen dims; drag a rectangle around
whatever has your attention — an error message, a maths problem, a
paragraph you're stuck on. Release, and Jev shows you the capture and
asks: *"What about it?"* Ask by typing, or hold the mic button (or
just press Space) and ask by voice:

> "what's this error?" · "solve 2x+7=15" · "reply to this email here"

Jev looks at the region with a small local vision model (**moondream**,
running on your machine through Ollama — nothing leaves your laptop),
answers in text and out loud, and shows you the capture it worked
from. If the answer leads somewhere actionable, tap **Do it with agent
mode**: your question is handed to the agent-mode planner, which can
chain the new read-only `see_capture` tool into real tools — so "reply
to this email here" can draft and, after the usual confirmation tap,
actually send the Gmail reply. The planner sees the capture; the
confirm gate still applies to every outward action.

**The privacy promise, plainly:** Jev only looks when you ask. The
screen capture happens only when you press the hotkey and draw a
region — never in the background, never continuous watching, never a
full screenshot. The capture lives only in memory, is never written to
disk, and expires on its own after 5 minutes (`JEV_SEE_CAPTURE_TTL_S`).
The region-select window says it on the tin: *"Jev only looks when
you ask."*

One-time setup on your laptop:

```bash
ollama pull moondream
```

That's the only new download — about 1.7 GB, free, local. If the model
isn't pulled yet, Jev tells you exactly which command to run instead
of guessing.

Developers: `POST /jev/see/capture` (multipart PNG; only called after
the explicit region select), `POST /jev/see` (question → answer +
timings), `GET /jev/see/status` (vision model availability). Settings:
`JEV_SEE_HOTKEY` (default `CommandOrControl+Shift+S`), `JEV_SEE_MODEL`
(default `moondream`), `JEV_SEE_CAPTURE_TTL_S` (default `300`).

---

### MCP — build your own integrations

The Model Context Protocol is an open standard for giving AI assistants
tools. Instead of Jev hand-writing every integration, it acts as an MCP
*client*: any community MCP server you list in `~/.jev/mcp.json` gets
connected at startup, and its tools appear in Jev as
`mcp.<server>.<tool>` — usable from plain chat and from agent-mode
plans, with outputs threading between steps like any built-in tool.

**Add a server (about 2 minutes):**

```bash
# 1. Install a community server — three verified examples:
pip install mcp-server-sqlite        # local SQLite database tools
pip install mcp-server-fetch         # fetch web pages as markdown
npx -y @modelcontextprotocol/server-filesystem  # local file tools (no install; npx fetches it)

# 2. Copy the example config and enable what you want:
cp docs/mcp.example.json ~/.jev/mcp.json
# then edit ~/.jev/mcp.json — set "enabled": true on your servers

# 3. Restart the backend (or POST /jev/mcp/refresh — no restart needed)
```

Then say *"list my MCP servers"* — or check `GET /jev/mcp/status` for
per-server availability, tool counts, and errors.

**Confirmation policy.** MCP tools follow the same gate as built-ins:
read-only tools run silently; anything that writes, sends, deletes, or
executes asks for your confirmation first. Per server you can set
`"confirm": "all"` (paranoid) or `"none"` (never ask — only for servers
you fully trust; not recommended).

**Security, plainly stated:**

- Only servers listed in `~/.jev/mcp.json` ever run. That file is the
  trust boundary — Jev never downloads, installs, or launches an MCP
  server on its own, and never adds entries to the file itself.
- A dead or hostile server can't break Jev: connections happen in the
  background, failures mark the server unavailable, and everything else
  keeps working.
- A remote (SSE) server sees every argument you send it. Only point Jev
  at servers you trust, especially remote ones.
- MCP tools never bypass the confirmation gate — there is no silent
  path around it.

**Honest limits:** MCP tools are only as good as their servers, and the
agent-mode planner only picks them when their descriptions match your
command — give your servers clear `"description"`-friendly names. The
fetch server needs outbound network access; on restricted machines it
will list its tools fine but fetches may fail.

Developers: `GET /jev/mcp/status`, `POST /jev/mcp/refresh`,
`GET /jev/status` (includes an `mcp` summary). The client lives in
`backend/app/services/jev/mcp_client.py`.

---

## 💻 Desktop app — install it, don't build it

Jev ships as a real desktop app: double-click the installer and it just
works. No terminal, no `npm run`, no manually starting the Python
backend — the installer bundles the frozen backend and the Electron
shell, which starts everything for you.

### How a release happens (automatic)

1. A version tag is pushed, e.g. `git tag v0.2.0 && git push origin v0.2.0`.
2. The `.github/workflows/release.yml` workflow builds the installers on
   GitHub-hosted runners — `windows-latest` (backend `.exe` frozen with
   PyInstaller + nsis installer), `macos-latest` (dmg), `ubuntu-latest`
   (AppImage). This is also what solves the Windows build problem: the
   `.exe` is compiled on a real Windows machine in the cloud.
3. A GitHub Release is created on the tag with all three installers
   attached. Download yours from the Releases page — that is the whole
   process; you never run a build command yourself.

### Building manually (optional)

Prerequisites per OS: Node 18+, Python 3.11+ with the backend venv
(`cd backend && uv sync`), and Ollama installed separately (see below).

```bash
cd frontend
npm run dist        # full installer for THIS machine's OS
npm run dist:dir    # unpacked app for testing (no installer)
npm run build:backend  # freeze the backend only (stages into resources/)
```

A Windows `.exe` must be built on Windows and the `.dmg` on macOS —
PyInstaller and electron-builder cannot cross-compile the backend.
The release workflow above handles this for you.

### First launch

- The backend starts automatically on a free local port; the app waits
  for its health check and shows a proper error dialog (never a blank
  screen) if something goes wrong. Backend logs live in the app-data
  `logs/backend.log`.
- **Ollama is not bundled** (multi-gigabyte weights). If it is missing,
  a setup screen walks you through installing it and running
  `ollama pull qwen2.5:1.5b`.
- **Whisper, Piper and wake-word models download on first use** into the
  app-data dir (Whisper → HuggingFace cache, Piper → `models/piper`,
  wake-word → openWakeWord cache). The installer stays small.
- Your data (databases, notes, OAuth tokens, settings) lives in the
  OS app-data dir (`~/.config/Jev` on Linux,
  `%APPDATA%/Jev` on Windows, `~/Library/Application Support/Jev` on macOS).

### Honest notes

- Installers are **unsigned** (code-signing certificates cost money): on
  first launch Windows SmartScreen may warn — choose *More info → Run
  anyway*; on macOS right-click the app → *Open*. This is normal for
  unsigned apps.
- The backend is a single-file executable that unpacks on each launch;
  if `/tmp` is tiny, set `TMPDIR` to a roomier directory.
- System tray: Show/Hide Jev, wake-word toggle, start-at-login, Quit.

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
