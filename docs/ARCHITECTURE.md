# Elysia Architecture

**Clean, Scalable, Future-Proof Design**

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Principles](#architecture-principles)
3. [High-Level Architecture](#high-level-architecture)
4. [Component Design](#component-design)
5. [Data Flow](#data-flow)
6. [API Design](#api-design)
7. [Security Architecture](#security-architecture)
8. [Scalability Considerations](#scalability-considerations)
9. [Technology Decisions](#technology-decisions)
10. [Future Architecture](#future-architecture)

---

## 1. System Overview

Elysia is built as a **three-tier architecture** with clear separation between presentation, business logic, and data layers.

```
┌─────────────────────────────────────────────┐
│         Frontend (Electron + React)          │
│  - UI Components                            │
│  - State Management                         │
│  - IPC with Main Process                    │
└─────────────────┬───────────────────────────┘
                  │ HTTP/WebSocket
┌─────────────────┴───────────────────────────┐
│         Backend (FastAPI + Python)           │
│  - REST API                                 │
│  - Business Logic                           │
│  - Service Layer                            │
└─────────────────┬───────────────────────────┘
                  │ Adapters
┌─────────────────┴───────────────────────────┐
│         External Services & Models           │
│  - LLM Providers (Ollama, OpenRouter, etc.)│
│  - STT (Faster-Whisper)                     │
│  - TTS (Piper)                              │
└─────────────────────────────────────────────┘
```

---

## 2. Architecture Principles

### SOLID Principles

**S — Single Responsibility**
- Each module has one reason to change
- Services handle one domain (STT, TTS, LLM, etc.)
- Clear boundaries between components

**O — Open/Closed**
- Open for extension (new LLM providers via interface)
- Closed for modification (core logic unchanged)
- Strategy pattern for provider selection

**L — Liskov Substitution**
- All LLM providers implement same interface
- STT/TTS providers are interchangeable
- No behavioral surprises on substitution

**I — Interface Segregation**
- Small, focused interfaces
- Clients depend only on methods they use
- No fat interfaces with unused methods

**D — Dependency Inversion**
- Depend on abstractions, not concretions
- Services injected via dependency injection
- Easy to test with mocks

### Additional Principles

**DRY (Don't Repeat Yourself)**
- Shared utilities in common modules
- Reusable components
- Configuration inheritance

**KISS (Keep It Simple, Stupid)**
- Simplest solution that works
- Avoid premature optimization
- Clear over clever

**YAGNI (You Aren't Gonna Need It)**
- Build what's needed now
- Architecture ready for future, but not implemented
- Avoid speculative features

---

## 3. High-Level Architecture

### Three-Layer Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER                       │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐    │
│  │  React UI   │  │   Electron   │  │   IPC       │    │
│  │  Components │  │ Main Process │  │   Bridge    │    │
│  └─────────────┘  └──────────────┘  └─────────────┘    │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP REST API
┌──────────────────────┴───────────────────────────────────┐
│                   BUSINESS LOGIC LAYER                    │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐    │
│  │   API       │  │   Services   │  │  Use Cases  │    │
│  │   Routes    │  │   (STT/LLM/  │  │  (Chat,     │    │
│  │             │  │    TTS)      │  │   Config)   │    │
│  └─────────────┘  └──────────────┘  └─────────────┘    │
└──────────────────────┬───────────────────────────────────┘
                       │ Provider Interfaces
┌──────────────────────┴───────────────────────────────────┐
│                   INFRASTRUCTURE LAYER                    │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐    │
│  │   LLM       │  │     STT      │  │     TTS     │    │
│  │  Providers  │  │   Providers  │  │  Providers  │    │
│  │  (Ollama,   │  │  (Whisper)   │  │  (Piper)    │    │
│  │  OpenRouter)│  │              │  │             │    │
│  └─────────────┘  └──────────────┘  └─────────────┘    │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Component Design

### 4.1 Frontend Architecture

**Technology:** React + TypeScript + Electron + TailwindCSS

```
frontend/
├── src/
│   ├── main/                    # Electron Main Process
│   │   ├── index.ts             # Entry point
│   │   ├── windowManager.ts     # Window lifecycle
│   │   ├── ipcHandlers.ts       # IPC message handlers
│   │   └── trayManager.ts       # System tray
│   │
│   ├── renderer/                # React Application
│   │   ├── App.tsx              # Root component
│   │   ├── components/          # UI Components
│   │   │   ├── Chat/            # Chat interface
│   │   │   │   ├── ChatWindow.tsx
│   │   │   │   ├── MessageList.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   └── InputControls.tsx
│   │   │   ├── Voice/           # Voice controls
│   │   │   │   ├── PushToTalkButton.tsx
│   │   │   │   ├── AudioVisualizer.tsx
│   │   │   │   └── TranscriptDisplay.tsx
│   │   │   ├── Settings/        # Settings UI
│   │   │   │   ├── SettingsPanel.tsx
│   │   │   │   ├── ProviderSelector.tsx
│   │   │   │   └── APIKeyInput.tsx
│   │   │   └── Common/          # Shared components
│   │   │       ├── Button.tsx
│   │   │       ├── Modal.tsx
│   │   │       └── Spinner.tsx
│   │   │
│   │   ├── hooks/               # Custom React hooks
│   │   │   ├── useVoice.ts      # Voice recording hook
│   │   │   ├── useChat.ts       # Chat state hook
│   │   │   ├── useSettings.ts   # Settings hook
│   │   │   └── useAudio.ts      # Audio playback hook
│   │   │
│   │   ├── services/            # API clients
│   │   │   ├── api.ts           # HTTP client
│   │   │   ├── chatService.ts   # Chat API
│   │   │   ├── voiceService.ts  # Voice API
│   │   │   └── settingsService.ts
│   │   │
│   │   ├── store/               # State management
│   │   │   ├── chatStore.ts     # Chat state (Zustand)
│   │   │   ├── settingsStore.ts # Settings state
│   │   │   └── uiStore.ts       # UI state
│   │   │
│   │   ├── types/               # TypeScript types
│   │   │   ├── chat.ts
│   │   │   ├── voice.ts
│   │   │   └── settings.ts
│   │   │
│   │   └── utils/               # Utilities
│   │       ├── audio.ts
│   │       ├── formatting.ts
│   │       └── validation.ts
│   │
│   └── preload/                 # Electron Preload
│       └── index.ts             # Expose safe APIs to renderer
```

**Design Patterns:**
- **Component Composition** — Small, reusable components
- **Custom Hooks** — Encapsulate stateful logic
- **Zustand Store** — Simple state management
- **API Service Layer** — Abstract HTTP calls

---

### 4.2 Backend Architecture

**Technology:** Python + FastAPI + Pydantic

```
backend/
├── app/
│   ├── main.py                  # FastAPI application entry
│   │
│   ├── api/                     # REST API Layer
│   │   ├── __init__.py
│   │   ├── deps.py              # Dependency injection
│   │   ├── v1/                  # API v1
│   │   │   ├── __init__.py
│   │   │   ├── router.py        # Main router
│   │   │   ├── chat.py          # Chat endpoints
│   │   │   ├── audio.py         # STT/TTS endpoints
│   │   │   ├── settings.py      # Settings endpoints
│   │   │   └── status.py        # Health check
│   │
│   ├── core/                    # Core Business Logic
│   │   ├── __init__.py
│   │   ├── config.py            # Configuration management
│   │   ├── logging.py           # Logging setup
│   │   ├── exceptions.py        # Custom exceptions
│   │   └── security.py          # Security utilities
│   │
│   ├── services/                # Service Layer
│   │   ├── __init__.py
│   │   ├── llm/                 # LLM Services
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Abstract base class
│   │   │   ├── ollama.py        # Ollama provider
│   │   │   ├── openrouter.py    # OpenRouter provider
│   │   │   ├── gemini.py        # Gemini provider
│   │   │   └── factory.py       # Provider factory
│   │   │
│   │   ├── stt/                 # Speech-to-Text
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Abstract base
│   │   │   └── whisper.py       # Faster-Whisper impl
│   │   │
│   │   ├── tts/                 # Text-to-Speech
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Abstract base
│   │   │   └── piper.py         # Piper TTS impl
│   │   │
│   │   ├── chat/                # Chat Service
│   │   │   ├── __init__.py
│   │   │   ├── conversation.py  # Conversation manager
│   │   │   └── streaming.py     # Streaming handler
│   │   │
│   │   └── audio/               # Audio Processing
│   │       ├── __init__.py
│   │       ├── recorder.py      # Audio recording
│   │       └── player.py        # Audio playback
│   │
│   ├── models/                  # Data Models
│   │   ├── __init__.py
│   │   ├── chat.py              # Chat schemas
│   │   ├── audio.py             # Audio schemas
│   │   ├── settings.py          # Settings schemas
│   │   └── response.py          # API responses
│   │
│   └── utils/                   # Utilities
│       ├── __init__.py
│       ├── helpers.py           # Helper functions
│       ├── validators.py        # Input validators
│       └── formatters.py        # Output formatters
```

**Design Patterns:**
- **Repository Pattern** — Data access abstraction (future)
- **Factory Pattern** — Provider creation
- **Strategy Pattern** — Provider selection
- **Dependency Injection** — Service composition
- **Adapter Pattern** — External service integration

---

## 5. Data Flow

### 5.1 Voice Conversation Flow

```
┌─────────┐
│  USER   │
└────┬────┘
     │ 1. Press Push-to-Talk
     ▼
┌─────────────────┐
│  Frontend UI    │ Record audio
└────┬────────────┘
     │ 2. Send audio bytes
     ▼
┌─────────────────┐
│  Backend API    │ POST /api/v1/audio/transcribe
└────┬────────────┘
     │ 3. Process audio
     ▼
┌─────────────────┐
│  STT Service    │ Faster-Whisper
└────┬────────────┘
     │ 4. Return text
     ▼
┌─────────────────┐
│  Chat Service   │ Build conversation context
└────┬────────────┘
     │ 5. Send to LLM
     ▼
┌─────────────────┐
│  LLM Service    │ Generate response (streaming)
└────┬────────────┘
     │ 6. Stream tokens
     ▼
┌─────────────────┐
│  Backend API    │ POST /api/v1/chat
└────┬────────────┘
     │ 7. Send chunks to frontend
     ▼
┌─────────────────┐
│  Frontend UI    │ Display streaming text
└────┬────────────┘
     │ 8. Send to TTS
     ▼
┌─────────────────┐
│  TTS Service    │ Piper synthesis
└────┬────────────┘
     │ 9. Return audio
     ▼
┌─────────────────┐
│  Frontend UI    │ Play audio
└─────────────────┘
```

### 5.2 Configuration Flow

```
┌──────────────┐
│  YAML Files  │ configs/settings.yaml
└──────┬───────┘
       │ Load on startup
       ▼
┌──────────────┐
│ .env File    │ Environment variables
└──────┬───────┘
       │ Override YAML
       ▼
┌──────────────┐
│ Config Class │ app/core/config.py
└──────┬───────┘
       │ Validate with Pydantic
       ▼
┌──────────────┐
│  Services    │ Injected into services
└──────────────┘
```

---

## 6. API Design

### RESTful API Structure

**Base URL:** `http://localhost:8000/api/v1`

#### Endpoints

**Chat**
```
POST   /chat                  # Send message, get streaming response
GET    /chat/history          # Get conversation history
DELETE /chat/history          # Clear history
```

**Audio**
```
POST   /audio/transcribe      # STT - audio to text
POST   /audio/synthesize      # TTS - text to audio
```

**Settings**
```
GET    /settings              # Get current settings
PUT    /settings              # Update settings
GET    /settings/providers    # List available providers
```

**Status**
```
GET    /status                # Health check
GET    /status/providers      # Provider status
```

### Request/Response Format

**Chat Request**
```json
{
  "message": "What is the weather today?",
  "conversation_id": "uuid-v4",
  "stream": true
}
```

**Chat Response (Streaming)**
```
data: {"type": "token", "content": "The "}
data: {"type": "token", "content": "weather "}
data: {"type": "token", "content": "today..."}
data: {"type": "done"}
```

**Settings Request**
```json
{
  "llm_provider": "ollama",
  "llm_model": "llama3.2",
  "tts_voice": "female_01",
  "api_keys": {
    "openrouter": "sk-..."
  }
}
```

---

## 7. Security Architecture

### API Key Management

```
User Input → .env File → Encrypted Config → Service Layer
                            (AES-256)
```

**Never:**
- Store keys in code
- Log keys
- Expose keys in API responses

**Always:**
- Encrypt at rest
- Use environment variables
- Validate and sanitize inputs

### Input Validation

```python
# Every request validated with Pydantic
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[UUID4] = None
    stream: bool = True
    
    @validator('message')
    def sanitize_message(cls, v):
        # Remove potential injection attacks
        return sanitize(v)
```

### Rate Limiting

```python
# Prevent abuse
@limiter.limit("60/minute")
async def chat_endpoint(...):
    ...
```

---

## 8. Scalability Considerations

### Phase 1 (Current)
- **Single-user desktop app**
- Local processing where possible
- No database needed yet

### Future Phases

**Horizontal Scaling**
- Load balancer → Multiple backend instances
- Stateless API design
- Shared session store (Redis)

**Caching**
- LLM response caching
- Configuration caching
- CDN for static assets

**Database**
- Phase 2: Vector DB for memory (Chroma)
- Phase 9: PostgreSQL for agents
- Phase 11: Cloud storage

---

## 9. Technology Decisions

### Why FastAPI?
- Modern async/await support
- Automatic API documentation
- Pydantic validation
- High performance
- Great developer experience

### Why Electron?
- Cross-platform (Windows, macOS, Linux)
- Web technologies for UI
- Native system access
- Large ecosystem

### Why React + TypeScript?
- Component-based architecture
- Type safety
- Rich ecosystem
- Easy state management

### Why Faster-Whisper?
- Local processing (privacy)
- Fast inference
- No API costs
- Offline capable

### Why Piper TTS?
- High-quality voices
- Local processing
- Open-source
- Low latency

---

## 10. Future Architecture

### Phase 2: Memory System

```
┌─────────────┐
│   LLM       │
└──────┬──────┘
       │ Query
       ▼
┌─────────────┐     ┌──────────────┐
│  RAG Engine │────►│  Vector DB   │
│             │     │  (Chroma)    │
└─────────────┘     └──────────────┘
```

### Phase 4: Plugin System

```
┌─────────────┐
│  Core App   │
└──────┬──────┘
       │ Load plugins
       ▼
┌─────────────┐     ┌──────────────┐
│  Plugin     │────►│  Sandbox     │
│  Loader     │     │  Environment │
└─────────────┘     └──────────────┘
       ▲
       │ Discover
       │
┌──────────────┐
│  Plugin      │
│  Registry    │
└──────────────┘
```

### Phase 9: Autonomous Agents

```
┌─────────────┐
│  Scheduler  │
└──────┬──────┘
       │ Trigger
       ▼
┌─────────────┐     ┌──────────────┐
│  Agent      │────►│  Task Queue  │
│  Manager    │     │  (Celery)    │
└─────────────┘     └──────────────┘
       ▲
       │ Monitor
       │
┌──────────────┐
│  State Store │
│  (Redis)     │
└──────────────┘
```

---

## Conclusion

This architecture is designed to:
- ✅ **Scale** from single-user to enterprise
- ✅ **Extend** without major refactoring
- ✅ **Maintain** with clear boundaries
- ✅ **Test** with dependency injection
- ✅ **Secure** with best practices

**Current Focus:** Phase 1 implementation with architecture ready for Phases 2-12.
