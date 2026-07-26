# Elysia Backend

FastAPI-based backend for the Elysia AI Operating System.

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Ollama (for local LLM) - [Download here](https://ollama.ai)

### Installation

```bash
# Install dependencies
uv sync

# Copy environment file
cp ../.env.example .env

# Edit .env and configure your settings
```

### Running

```bash
# Start the server
uv run python -m app.main

# Or use the entry point
uv run elysia
```

The server will start on `http://localhost:8000`

### Testing

```bash
# Health check
curl http://localhost:8000/health

# Status endpoint
curl http://localhost:8000/api/v1/status

# Chat (non-streaming)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, Elysia",
    "stream": false
  }'

# Chat (streaming)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about yourself",
    "stream": true
  }'
```

## API Documentation

When running in debug mode, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
backend/
├── app/
│   ├── api/              # API endpoints
│   │   └── v1/           # API v1
│   │       ├── chat.py   # Chat endpoints
│   │       ├── status.py # Status endpoints
│   │       └── router.py # Main router
│   │
│   ├── core/             # Core functionality
│   │   ├── config.py     # Configuration
│   │   ├── logging.py    # Logging setup
│   │   └── exceptions.py # Custom exceptions
│   │
│   ├── models/           # Data models
│   │   └── chat.py       # Chat schemas
│   │
│   ├── services/         # Business logic
│   │   ├── llm/          # LLM providers
│   │   │   ├── base.py   # Abstract base
│   │   │   ├── ollama.py # Ollama impl
│   │   │   └── factory.py# Provider factory
│   │   │
│   │   └── chat/         # Chat services
│   │       └── conversation.py # History mgmt
│   │
│   └── main.py           # Application entry
│
├── pyproject.toml        # Dependencies
└── README.md             # This file
```

## Configuration

Configuration is managed through environment variables (`.env` file):

```bash
# Server
HOST=127.0.0.1
PORT=8000
DEBUG=false

# LLM
DEFAULT_LLM_PROVIDER=ollama
DEFAULT_LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/elysia.log
```

## Development

### Code Style

```bash
# Format code
uv run black app/

# Lint code
uv run ruff check app/

# Type check
uv run mypy app/
```

### Testing

```bash
# Run tests
uv run pytest

# With coverage
uv run pytest --cov=app
```

## Troubleshooting

### Ollama Connection Error

**Error:** `Cannot connect to Ollama at http://localhost:11434`

**Solution:**
1. Install Ollama from https://ollama.ai
2. Start Ollama: `ollama serve`
3. Pull a model: `ollama pull llama3.2`

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'app'`

**Solution:** Run from the backend directory:
```bash
cd backend
uv run python -m app.main
```

### Port Already in Use

**Error:** `Address already in use`

**Solution:** Change port in `.env`:
```bash
PORT=8001
```

## Phase 1 Status

✅ **Complete:**
- FastAPI application setup
- Configuration management
- Logging infrastructure
- Exception handling
- Chat API endpoints
- Ollama LLM provider
- Conversation management
- Streaming responses

❌ **Not Yet Implemented:**
- STT (Speech-to-Text) service
- TTS (Text-to-Speech) service
- OpenRouter provider
- Gemini provider
- Audio endpoints

## Next Steps

1. Test backend with Ollama
2. Implement audio services (STT/TTS)
3. Build frontend UI
4. Integrate voice pipeline

## Documentation

- [API Specification](../docs/API_SPEC.md)
- [Architecture](../docs/ARCHITECTURE.md)
- [Coding Standards](../docs/CODING_STANDARDS.md)

## License

MIT - See [LICENSE](../LICENSE)
