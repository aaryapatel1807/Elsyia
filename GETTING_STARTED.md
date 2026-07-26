# Getting Started with Elysia

**Quick guide to running the Elysia AI Operating System**

---

## 📋 Prerequisites

Before you begin, ensure you have:

### Required
- ✅ **Python 3.11+** - [Download](https://www.python.org/downloads/)
- ✅ **Node.js 18+** - [Download](https://nodejs.org/)
- ✅ **uv** - Python package manager
  ```bash
  pip install uv
  ```
- ✅ **Ollama** - Local LLM runtime
  ```bash
  # Download from https://ollama.ai
  # Or use package manager:
  # Windows: winget install Ollama.Ollama
  # macOS: brew install ollama
  ```

### Optional (for development)
- Git
- VSCode or your preferred IDE
- Postman or similar API testing tool

---

## 🚀 Quick Start (5 minutes)

### Step 1: Clone/Download Project

```bash
# If you have git
git clone https://github.com/yourusername/elysia.git
cd elysia

# Or just extract the elysia folder
cd elysia
```

### Step 2: Setup Ollama

```bash
# Start Ollama server
ollama serve

# In another terminal, pull a model
ollama pull llama3.2

# Verify it works
ollama run llama3.2 "Hello"
```

### Step 3: Configure Backend

```bash
cd backend

# Create environment file
cp ../.env.example .env

# Edit .env if needed (optional for local Ollama)
# The defaults work out of the box!
```

### Step 4: Install & Run Backend

```bash
# Install dependencies
uv sync

# Start the server
uv run python -m app.main
```

You should see:
```
🚀 Elysia Backend starting...
Environment: Production
Default LLM: ollama/llama3.2
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Step 5: Test It!

Open a new terminal:

```bash
cd backend

# Run test script
uv run python test_api.py
```

Or test manually:
```bash
curl http://localhost:8000/health
```

---

## 🧪 Testing the Backend

### Method 1: Test Script (Recommended)

```bash
cd backend
uv run python test_api.py
```

This will test all endpoints and show you exactly what works.

### Method 2: Manual curl Commands

```bash
# Health check
curl http://localhost:8000/health

# Status
curl http://localhost:8000/api/v1/status

# Chat (non-streaming)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, Elysia! Introduce yourself.",
    "stream": false
  }'

# Chat (streaming)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Count from 1 to 5",
    "stream": true
  }'
```

### Method 3: API Documentation

Visit http://localhost:8000/docs (when DEBUG=true) for interactive Swagger UI.

---

## 📁 Project Structure Overview

```
elysia/
├── docs/              # 📚 All documentation
├── backend/           # 🐍 Python FastAPI server
├── frontend/          # ⚛️ React + Electron (not yet built)
├── prompts/           # 🤖 AI system prompts
├── configs/           # ⚙️ Configuration files
├── .env.example       # 🔐 Environment template
└── README.md          # 📖 Main readme
```

---

## ⚙️ Configuration

### Environment Variables (.env)

The backend uses `.env` for configuration. Copy `.env.example` to `.env`:

```bash
# Ollama (works out of the box)
OLLAMA_BASE_URL=http://localhost:11434

# Optional: Add API keys for other providers
OPENROUTER_API_KEY=your-key-here
GOOGLE_API_KEY=your-key-here

# Server settings (defaults work fine)
HOST=127.0.0.1
PORT=8000
DEBUG=false

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/elysia.log
```

### YAML Configuration

Edit `configs/settings.yaml` for advanced settings:
- LLM provider configs
- Audio settings
- Performance tuning
- Feature flags

---

## 🎯 What Works Right Now

### ✅ Fully Working
- REST API server
- Chat endpoints
- Conversation history
- Ollama integration
- Streaming responses
- Error handling
- Logging

### ⏳ Coming Soon (Phase 1)
- Speech-to-Text (Whisper)
- Text-to-Speech (Piper)
- Desktop UI (Electron + React)
- Audio endpoints
- OpenRouter provider
- Gemini provider

### 🔮 Future Phases (2-12)
- Memory system
- Vision capabilities
- Plugins
- Desktop/Browser automation
- And much more...

See [ROADMAP.md](docs/ROADMAP.md) for complete vision.

---

## 🐛 Troubleshooting

### "Cannot connect to Ollama"

**Problem:** Backend can't reach Ollama server.

**Solutions:**
1. Check if Ollama is running: `ollama serve`
2. Verify URL in `.env`: `OLLAMA_BASE_URL=http://localhost:11434`
3. Test Ollama directly: `ollama run llama3.2 "test"`

### "No module named 'app'"

**Problem:** Python can't find the app module.

**Solution:** Run from backend directory:
```bash
cd backend
uv run python -m app.main
```

### "Model not found"

**Problem:** Ollama model not downloaded.

**Solution:**
```bash
ollama pull llama3.2
ollama list  # verify it's there
```

### "Port already in use"

**Problem:** Port 8000 is taken.

**Solution:** Change port in `.env`:
```bash
PORT=8001
```

### "Import errors with dependencies"

**Problem:** Dependencies not installed correctly.

**Solution:**
```bash
cd backend
rm -rf .venv  # or delete .venv folder
uv sync       # reinstall
```

---

## 🎓 Next Steps

### 1. Understand the Architecture

Read these docs in order:
1. [README.md](README.md) - Overview
2. [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design
3. [API_SPEC.md](docs/API_SPEC.md) - API reference

### 2. Explore the Code

Start with:
- `backend/app/main.py` - Application entry point
- `backend/app/api/v1/chat.py` - Chat endpoints
- `backend/app/services/llm/ollama.py` - Ollama integration

### 3. Make Your First Change

Try:
- Change the system prompt in `prompts/elysia.txt`
- Add a new endpoint in `backend/app/api/v1/`
- Modify LLM temperature in `.env`

### 4. Build the Frontend

Follow [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) to:
- Set up Electron + React
- Build the UI
- Connect to backend
- Complete the voice pipeline

---

## 📚 Documentation

All docs are in the `docs/` folder:

**Essential Reading:**
- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design
- [API_SPEC.md](docs/API_SPEC.md) - API documentation

**Understanding the Project:**
- [PRD.md](docs/PRD.md) - Product requirements
- [ROADMAP.md](docs/ROADMAP.md) - 12-phase plan
- [PERSONALITY.md](docs/PERSONALITY.md) - AI character

**Development:**
- [CODING_STANDARDS.md](docs/CODING_STANDARDS.md) - Code guidelines
- [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) - How to build
- [PROJECT_STATUS.md](PROJECT_STATUS.md) - Current progress

---

## 💡 Tips

### Development Workflow

```bash
# Terminal 1: Backend
cd backend
uv run python -m app.main

# Terminal 2: Testing
cd backend
uv run python test_api.py

# Terminal 3: Ollama (if not running as service)
ollama serve
```

### Hot Reload

Enable in `.env`:
```bash
DEBUG=true
```

Now the server reloads on code changes!

### Viewing Logs

```bash
tail -f backend/logs/elysia.log
```

### API Documentation

Visit http://localhost:8000/docs when DEBUG=true.

---

## 🤝 Getting Help

### Documentation
- Check `docs/` folder first
- Read `SUMMARY.md` for overview
- See `IMPLEMENTATION_GUIDE.md` for code examples

### Debugging
- Check logs: `backend/logs/elysia.log`
- Enable DEBUG mode in `.env`
- Run test script: `test_api.py`

### Common Issues
- See **Troubleshooting** section above
- Check Ollama is running
- Verify Python 3.11+
- Ensure uv is installed

---

## 🎉 Success!

If you can:
1. ✅ Start the backend server
2. ✅ Run `test_api.py` successfully
3. ✅ Get responses from Ollama
4. ✅ See conversation history

Then **you're ready to develop!**

---

## 🚀 What's Next?

Choose your path:

### Path A: Complete Backend
- Add OpenRouter provider
- Add Gemini provider
- Implement STT/TTS
- Add audio endpoints

### Path B: Build Frontend
- Set up Electron + React
- Create chat UI
- Connect to backend
- Add voice controls

### Path C: Test & Polish
- Write tests
- Improve error handling
- Add features
- Polish UI

**See [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for detailed steps.**

---

## 📞 Quick Reference

### Start Backend
```bash
cd backend && uv run python -m app.main
```

### Test Backend
```bash
cd backend && uv run python test_api.py
```

### Check Health
```bash
curl http://localhost:8000/health
```

### View Logs
```bash
tail -f backend/logs/elysia.log
```

### Stop Server
Press `Ctrl+C` in the terminal

---

**Welcome to Elysia! Happy building! 🚀**
