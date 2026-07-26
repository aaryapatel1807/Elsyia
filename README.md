# Elysia

**The AI that understands, remembers, and acts.**

![Version](https://img.shields.io/badge/version-0.1.0--alpha-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Phase](https://img.shields.io/badge/phase-1-orange)

---

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

> **Note:** Phase 1 is under active development.

### Prerequisites
- **Node.js** 18+
- **Python** 3.11+
- **uv** (Python package manager)

### Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/elysia.git
cd elysia

# Backend setup
cd backend
uv sync
cp .env.example .env
# Edit .env with your API keys

# Start backend
uv run python main.py

# Frontend setup (separate terminal)
cd frontend
npm install

# Start frontend
npm run dev
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
