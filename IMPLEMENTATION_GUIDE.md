# Elysia Implementation Guide

**Complete Guide for Building Phase 1**

---

## Overview

This guide provides step-by-step instructions for completing the Elysia Phase 1 implementation. The foundation (documentation, architecture, core backend files) is already in place. This guide covers what remains.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- uv (Python package manager): `pip install uv`
- Basic understanding of FastAPI and React

---

## Part 1: Complete Backend Implementation

### Step 1: Create LLM Service Base

**File:** `backend/app/services/llm/base.py`

```python
"""Base LLM Provider Interface"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate response from LLM.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            
        Yields:
            Response tokens
        """
        pass
    
    @abstractmethod
    async def get_available_models(self) -> list[str]:
        """Get list of available models."""
        pass
```

### Step 2: Implement Ollama Provider

**File:** `backend/app/services/llm/ollama.py`

```python
"""Ollama LLM Provider"""

import httpx
from typing import AsyncGenerator, Optional

from app.core import LLMError, get_logger
from app.services.llm.base import LLMProvider

logger = get_logger("llm.ollama")


class OllamaProvider(LLMProvider):
    """Ollama provider implementation."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Generate response from Ollama."""
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": "llama3.2",
                "prompt": prompt,
                "system": system_prompt or "",
                "temperature": temperature,
                "stream": True,
            }
            
            async with self.client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    raise LLMError(
                        f"Ollama returned {response.status_code}",
                        provider="ollama"
                    )
                
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]
        
        except httpx.TimeoutException:
            raise LLMError("Ollama request timed out", provider="ollama")
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise LLMError(str(e), provider="ollama")
    
    async def get_available_models(self) -> list[str]:
        """Get available Ollama models."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            data = response.json()
            return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []
```

### Step 3: Create LLM Factory

**File:** `backend/app/services/llm/factory.py`

```python
"""LLM Provider Factory"""

from typing import Literal

from app.core import ConfigurationError, get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.ollama import OllamaProvider
# Future: from app.services.llm.openrouter import OpenRouterProvider
# Future: from app.services.llm.gemini import GeminiProvider


def create_llm_provider(
    provider: Literal["ollama", "openrouter", "gemini"]
) -> LLMProvider:
    """
    Create LLM provider instance.
    
    Args:
        provider: Provider name
        
    Returns:
        LLM provider instance
        
    Raises:
        ConfigurationError: If provider is unknown
    """
    settings = get_settings()
    
    if provider == "ollama":
        return OllamaProvider(base_url=settings.OLLAMA_BASE_URL)
    # elif provider == "openrouter":
    #     return OpenRouterProvider(api_key=settings.OPENROUTER_API_KEY)
    # elif provider == "gemini":
    #     return GeminiProvider(api_key=settings.GOOGLE_API_KEY)
    else:
        raise ConfigurationError(f"Unknown LLM provider: {provider}")
```

### Step 4: Create Chat Service

**File:** `backend/app/services/chat/conversation.py`

```python
"""Conversation Management Service"""

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID, uuid4

from app.models import Message, MessageRole, ConversationHistory


class ConversationManager:
    """Manages conversation history."""
    
    def __init__(self):
        self._conversations: Dict[UUID, ConversationHistory] = {}
    
    def get_or_create(self, conversation_id: Optional[UUID] = None) -> ConversationHistory:
        """Get existing conversation or create new one."""
        if conversation_id is None:
            conversation_id = uuid4()
        
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = ConversationHistory(
                conversation_id=conversation_id,
                messages=[],
            )
        
        return self._conversations[conversation_id]
    
    def add_message(self, conversation_id: UUID, role: MessageRole, content: str):
        """Add message to conversation."""
        conversation = self.get_or_create(conversation_id)
        message = Message(role=role, content=content)
        conversation.messages.append(message)
        conversation.updated_at = datetime.utcnow()
    
    def get_history(self, conversation_id: UUID) -> Optional[ConversationHistory]:
        """Get conversation history."""
        return self._conversations.get(conversation_id)
    
    def clear(self, conversation_id: UUID):
        """Clear conversation history."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
    
    def format_for_llm(self, conversation_id: UUID, system_prompt: str) -> str:
        """Format conversation for LLM."""
        conversation = self.get_or_create(conversation_id)
        
        formatted = f"System: {system_prompt}\n\n"
        for msg in conversation.messages:
            formatted += f"{msg.role.value.capitalize()}: {msg.content}\n"
        
        return formatted


# Global instance
conversation_manager = ConversationManager()
```

### Step 5: Create API Router

**File:** `backend/app/api/v1/router.py`

```python
"""API v1 Router"""

from fastapi import APIRouter

from app.api.v1 import chat, status

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(status.router, prefix="/status", tags=["status"])
```

### Step 6: Create Chat Endpoints

**File:** `backend/app/api/v1/chat.py`

```python
"""Chat API Endpoints"""

from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core import get_logger, get_settings, LLMError
from app.models import ChatRequest, ChatResponse, StreamChunk, MessageRole
from app.services.llm.factory import create_llm_provider
from app.services.chat.conversation import conversation_manager

logger = get_logger("api.chat")
router = APIRouter()


# Load system prompt
with open("prompts/elysia.txt", "r") as f:
    SYSTEM_PROMPT = f.read()


@router.post("/")
async def chat(request: ChatRequest):
    """
    Chat endpoint - send message and receive response.
    
    Supports both streaming and non-streaming modes.
    """
    settings = get_settings()
    
    # Get provider
    provider_name = request.provider or settings.DEFAULT_LLM_PROVIDER
    try:
        llm = create_llm_provider(provider_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Get or create conversation
    conversation = conversation_manager.get_or_create(request.conversation_id)
    conv_id = conversation.conversation_id
    
    # Add user message
    conversation_manager.add_message(conv_id, MessageRole.USER, request.message)
    
    # Format prompt
    context = conversation_manager.format_for_llm(conv_id, SYSTEM_PROMPT)
    prompt = f"{context}Assistant: "
    
    if request.stream:
        # Streaming response
        async def generate() -> AsyncGenerator[str, None]:
            try:
                full_response = ""
                async for token in llm.generate(prompt, temperature=request.temperature or 0.7):
                    full_response += token
                    chunk = StreamChunk(type="token", content=token)
                    yield f"data: {chunk.model_dump_json()}\n\n"
                
                # Save assistant response
                conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, full_response)
                
                # Send done signal
                done = StreamChunk(type="done", conversation_id=conv_id)
                yield f"data: {done.model_dump_json()}\n\n"
            
            except LLMError as e:
                error = StreamChunk(type="error", error=str(e))
                yield f"data: {error.model_dump_json()}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    else:
        # Non-streaming response
        try:
            full_response = ""
            async for token in llm.generate(prompt):
                full_response += token
            
            conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, full_response)
            
            return ChatResponse(
                response=full_response,
                conversation_id=conv_id,
                model=request.model or settings.DEFAULT_LLM_MODEL,
            )
        
        except LLMError as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{conversation_id}")
async def get_history(conversation_id: UUID):
    """Get conversation history."""
    history = conversation_manager.get_history(conversation_id)
    if not history:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return history


@router.delete("/history/{conversation_id}")
async def clear_history(conversation_id: UUID):
    """Clear conversation history."""
    conversation_manager.clear(conversation_id)
    return {"status": "cleared", "conversation_id": conversation_id}
```

### Step 7: Create Status Endpoints

**File:** `backend/app/api/v1/status.py`

```python
"""Status API Endpoints"""

from fastapi import APIRouter

from app.core import get_settings

router = APIRouter()


@router.get("/")
async def get_status():
    """Get API status."""
    return {
        "status": "ok",
        "version": "0.1.0",
        "phase": 1,
    }


@router.get("/providers")
async def get_providers():
    """Get available providers and their status."""
    settings = get_settings()
    
    return {
        "llm": {
            "default": settings.DEFAULT_LLM_PROVIDER,
            "available": ["ollama"],  # Add more as implemented
        },
        "stt": {
            "default": settings.DEFAULT_STT_PROVIDER,
            "available": ["whisper"],
        },
        "tts": {
            "default": settings.DEFAULT_TTS_PROVIDER,
            "available": ["piper"],
        },
    }
```

### Step 8: Create __init__ files

Create empty `__init__.py` files in:
- `backend/app/api/__init__.py`
- `backend/app/api/v1/__init__.py`
- `backend/app/services/__init__.py`
- `backend/app/services/llm/__init__.py`
- `backend/app/services/chat/__init__.py`

### Step 9: Test Backend

```bash
cd backend
uv sync
uv run python -m app.main
```

Test with curl:
```bash
curl http://localhost:8000/
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, Elysia", "stream": false}'
```

---

## Part 2: Frontend Implementation

### Step 1: Initialize Frontend

```bash
cd frontend
npm init -y
npm install react react-dom electron
npm install -D @vitejs/plugin-react typescript vite electron-builder
npm install -D tailwindcss postcss autoprefixer
npm install zustand axios
```

### Step 2: Create package.json scripts

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "electron": "electron .",
    "electron:dev": "concurrently \"npm run dev\" \"wait-on http://localhost:5173 && electron .\"" 
  }
}
```

### Step 3: Create Basic UI

See frontend structure in ARCHITECTURE.md and implement:
- Electron main process
- React app with chat UI
- Push-to-talk button
- API client for backend
- Audio recording and playback

---

## Part 3: Integration & Testing

1. Start backend: `cd backend && uv run python -m app.main`
2. Start frontend: `cd frontend && npm run electron:dev`
3. Test voice flow end-to-end
4. Fix bugs and polish

---

## Next Steps

1. **Implement STT/TTS services** (Phase 1 complete without voice is still valuable)
2. **Build frontend UI**
3. **Add settings panel**
4. **Polish and test**
5. **Package for distribution**

---

## Resources

- FastAPI: https://fastapi.tiangolo.com
- Electron: https://www.electronjs.org
- React: https://react.dev
- Zustand: https://github.com/pmndrs/zustand

---

**You've got a solid foundation. Time to build!** 🚀
