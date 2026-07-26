# Elysia API Specification

**REST API v1 Documentation**

Base URL: `http://localhost:8000/api/v1`

---

## Authentication

Phase 1: No authentication (local desktop app)  
Future: API keys, OAuth2

---

## Endpoints

### Health Check

#### `GET /status`

Check if the server is running.

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "phase": 1
}
```

---

### Chat

#### `POST /chat`

Send a message and receive AI response (streaming or complete).

**Request:**
```json
{
  "message": "Hello, Elysia",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "stream": true,
  "provider": "ollama",
  "model": "llama3.2"
}
```

**Parameters:**
- `message` (string, required): User message
- `conversation_id` (UUID, optional): Session identifier
- `stream` (boolean, default: true): Stream response
- `provider` (string, optional): Override LLM provider
- `model` (string, optional): Override model

**Response (Streaming):**
```
data: {"type": "token", "content": "Hello"}
data: {"type": "token", "content": "!"}
data: {"type": "token", "content": " How"}
data: {"type": "done", "conversation_id": "550e8400-e29b-41d4-a716-446655440000"}
```

**Response (Non-Streaming):**
```json
{
  "response": "Hello! How can I help you today?",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "tokens_used": 42
}
```

---

#### `GET /chat/history`

Get conversation history for a session.

**Parameters:**
- `conversation_id` (UUID, required): Session identifier

**Response:**
```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {
      "role": "user",
      "content": "Hello",
      "timestamp": "2025-01-15T10:30:00Z"
    },
    {
      "role": "assistant",
      "content": "Hello! How can I help?",
      "timestamp": "2025-01-15T10:30:02Z"
    }
  ]
}
```

---

#### `DELETE /chat/history`

Clear conversation history.

**Parameters:**
- `conversation_id` (UUID, required): Session to clear

**Response:**
```json
{
  "status": "cleared",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### Audio

#### `POST /audio/transcribe`

Convert speech to text.

**Request:**
Content-Type: `multipart/form-data`

- `audio`: Audio file (WAV, MP3, OGG)
- `language`: Language code (optional, default: "en")

**Response:**
```json
{
  "text": "Hello, Elysia, how are you?",
  "language": "en",
  "duration": 2.5
}
```

---

#### `POST /audio/synthesize`

Convert text to speech.

**Request:**
```json
{
  "text": "Hello, how can I help you today?",
  "voice": "female_01",
  "speed": 1.0
}
```

**Response:**
Content-Type: `audio/wav`

Binary audio data

---

### Settings

#### `GET /settings`

Get current configuration.

**Response:**
```json
{
  "llm": {
    "provider": "ollama",
    "model": "llama3.2",
    "temperature": 0.7
  },
  "stt": {
    "provider": "whisper",
    "model": "base",
    "language": "en"
  },
  "tts": {
    "provider": "piper",
    "voice": "female_01",
    "speed": 1.0
  },
  "ui": {
    "theme": "dark"
  }
}
```

---

#### `PUT /settings`

Update configuration.

**Request:**
```json
{
  "llm": {
    "provider": "openrouter",
    "model": "anthropic/claude-3.5-sonnet"
  }
}
```

**Response:**
```json
{
  "status": "updated",
  "settings": { /* updated settings */ }
}
```

---

#### `GET /settings/providers`

List available providers and models.

**Response:**
```json
{
  "llm": [
    {
      "provider": "ollama",
      "models": ["llama3.2", "mistral", "phi3"]
    },
    {
      "provider": "openrouter",
      "models": ["anthropic/claude-3.5-sonnet", "openai/gpt-4"]
    }
  ],
  "stt": [
    {"provider": "whisper", "models": ["tiny", "base", "small"]}
  ],
  "tts": [
    {"provider": "piper", "voices": ["female_01", "male_01"]}
  ]
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "Message cannot be empty",
    "details": { /* optional additional info */ }
  }
}
```

### Error Codes

- `INVALID_REQUEST` — Malformed request
- `PROVIDER_ERROR` — LLM/STT/TTS provider failed
- `NOT_FOUND` — Resource not found
- `RATE_LIMIT` — Too many requests
- `INTERNAL_ERROR` — Server error

---

## Rate Limiting

Phase 1: No rate limiting (local use)  
Future: 60 requests/minute per user

---

## Versioning

Current version: `v1`

Breaking changes will result in new version (`v2`, etc.)
