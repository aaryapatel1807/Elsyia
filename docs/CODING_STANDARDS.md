# Elysia Coding Standards

**Development Guidelines for Production-Quality Code**

---

## Philosophy

1. **Code is read more than written** — Optimize for clarity
2. **Simple is better than clever** — KISS principle
3. **Explicit is better than implicit** — No magic
4. **Consistency matters** — Follow established patterns
5. **Test what matters** — Focus on business logic

---

## Python Standards

### Style Guide

Follow **PEP 8** with these additions:

**Line Length:** 100 characters (not 79)  
**Imports:** Absolute imports, grouped and sorted  
**Quotes:** Double quotes `"` for strings  
**Type Hints:** Required for all public functions

### Example

```python
from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    
    message: str
    conversation_id: Optional[str] = None
    stream: bool = True
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "message": "Hello, Elysia",
                "stream": True
            }
        }


async def process_chat(
    request: ChatRequest,
    llm_service: LLMService
) -> AsyncGenerator[str, None]:
    """
    Process chat request and stream response.
    
    Args:
        request: Chat request containing message and options
        llm_service: LLM service instance
        
    Yields:
        Response tokens as they're generated
        
    Raises:
        ProviderError: If LLM provider fails
    """
    # Implementation
    pass
```

### Naming Conventions

- **Functions/Methods:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_SNAKE_CASE`
- **Private:** `_leading_underscore`
- **Files:** `snake_case.py`
- **Modules:** `lowercase` or `snake_case`

### Docstrings

Use **Google Style** docstrings:

```python
def function(arg1: str, arg2: int) -> bool:
    """
    Short description.
    
    Longer description if needed.
    
    Args:
        arg1: Description of arg1
        arg2: Description of arg2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When this happens
    """
```

---

## TypeScript Standards

### Style Guide

Follow **Airbnb Style Guide** with these additions:

**Semicolons:** Yes, always  
**Quotes:** Double quotes `"` for strings  
**Indentation:** 2 spaces  
**Type Annotations:** Required for function parameters and returns

### Example

```typescript
import { useState, useEffect } from "react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

export const ChatWindow: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState<string>("");
  
  const sendMessage = async (message: string): Promise<void> => {
    // Implementation
  };
  
  return (
    <div className="chat-window">
      {/* Component JSX */}
    </div>
  );
};
```

### Naming Conventions

- **Components:** `PascalCase`
- **Functions:** `camelCase`
- **Hooks:** `useCamelCase`
- **Constants:** `UPPER_SNAKE_CASE`
- **Interfaces:** `PascalCase` (no `I` prefix)
- **Types:** `PascalCase`
- **Files:** `PascalCase.tsx` for components, `camelCase.ts` for utilities

---

## Project Structure Rules

### Backend

```python
# ✅ Good: Clear responsibility
backend/app/services/llm/ollama.py

# ❌ Bad: Mixed concerns
backend/app/llm_and_tts_stuff.py
```

### Frontend

```typescript
// ✅ Good: Feature-based folders
src/renderer/components/Chat/MessageList.tsx

// ❌ Bad: Flat structure
src/renderer/components/message-list.tsx
```

---

## SOLID Principles

### Single Responsibility

```python
# ✅ Good
class OllamaProvider(LLMProvider):
    """Handles Ollama API communication only."""
    pass

class ChatService:
    """Manages conversation logic only."""
    pass

# ❌ Bad
class ChatHandler:
    """Does everything: LLM, TTS, STT, UI..."""
    pass
```

### Open/Closed

```python
# ✅ Good: Open for extension
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> AsyncGenerator:
        pass

class OllamaProvider(LLMProvider):
    async def generate(self, prompt: str) -> AsyncGenerator:
        # Ollama implementation
        pass

# ❌ Bad: Modification required for new providers
def generate_response(prompt: str, provider: str):
    if provider == "ollama":
        # ...
    elif provider == "openrouter":
        # ...
    # Need to modify this function for every new provider!
```

### Dependency Inversion

```python
# ✅ Good: Depend on abstraction
class ChatService:
    def __init__(self, llm: LLMProvider):  # Abstract base
        self.llm = llm

# ❌ Bad: Depend on concrete implementation
class ChatService:
    def __init__(self):
        self.llm = OllamaProvider()  # Hardcoded!
```

---

## Error Handling

### Python

```python
# ✅ Good: Specific exceptions
class ProviderError(Exception):
    """LLM provider failed."""
    pass

try:
    result = await llm.generate(prompt)
except httpx.TimeoutException as e:
    logger.error(f"LLM timeout: {e}")
    raise ProviderError("LLM request timed out") from e

# ❌ Bad: Bare except
try:
    result = await llm.generate(prompt)
except:  # What are we catching?!
    pass  # Silent failure!
```

### TypeScript

```typescript
// ✅ Good: Typed errors
class APIError extends Error {
  constructor(
    message: string,
    public statusCode: number
  ) {
    super(message);
    this.name = "APIError";
  }
}

try {
  await sendMessage(text);
} catch (error) {
  if (error instanceof APIError) {
    // Handle API error
  } else {
    // Handle unknown error
  }
}

// ❌ Bad: Swallow errors
try {
  await sendMessage(text);
} catch {
  // Ignored!
}
```

---

## Testing

### Test Structure

```python
# tests/services/test_ollama.py

import pytest
from app.services.llm.ollama import OllamaProvider


@pytest.fixture
def ollama_provider():
    """Create test provider instance."""
    return OllamaProvider(base_url="http://localhost:11434")


@pytest.mark.asyncio
async def test_generate_response(ollama_provider):
    """Test basic response generation."""
    # Arrange
    prompt = "Hello"
    
    # Act
    response = ""
    async for token in ollama_provider.generate(prompt):
        response += token
    
    # Assert
    assert len(response) > 0
    assert isinstance(response, str)


@pytest.mark.asyncio
async def test_generate_handles_timeout(ollama_provider, mocker):
    """Test timeout handling."""
    # Arrange
    mocker.patch("httpx.AsyncClient.post", side_effect=TimeoutException)
    
    # Act & Assert
    with pytest.raises(ProviderError):
        async for _ in ollama_provider.generate("test"):
            pass
```

### Test Naming

- `test_<function>_<scenario>_<expected>`
- Example: `test_transcribe_empty_audio_raises_error`

---

## Git Workflow

### Commit Messages

```
feat: Add Ollama LLM provider support
fix: Resolve audio streaming latency issue
docs: Update API specification
refactor: Simplify chat service logic
test: Add tests for TTS synthesis
chore: Update dependencies
```

### Branch Naming

- `feature/ollama-provider`
- `fix/audio-latency`
- `docs/api-spec`
- `refactor/chat-service`

---

## Code Review Checklist

Before submitting code:

- [ ] Follows style guide (use formatters!)
- [ ] Has type hints/annotations
- [ ] Includes docstrings
- [ ] No commented-out code
- [ ] No hardcoded values (use config)
- [ ] Error handling implemented
- [ ] Tests included (if appropriate)
- [ ] No console.log / print statements (use logging)
- [ ] No security issues (API keys, etc.)
- [ ] Documentation updated

---

## Tools

### Python

- **Formatter:** `black`
- **Linter:** `ruff`
- **Type Checker:** `mypy`
- **Test Runner:** `pytest`

### TypeScript

- **Formatter:** `prettier`
- **Linter:** `eslint`
- **Type Checker:** `tsc`
- **Test Runner:** `vitest`

### Configuration

All tools configured in project root:
- `pyproject.toml` (Python)
- `.eslintrc.js` (ESLint)
- `.prettierrc` (Prettier)

---

## Performance Guidelines

### Do

- ✅ Use async/await for I/O
- ✅ Stream responses when possible
- ✅ Cache expensive computations
- ✅ Lazy-load components
- ✅ Debounce user input

### Don't

- ❌ Block the event loop
- ❌ Load everything upfront
- ❌ Make synchronous API calls
- ❌ Re-render entire UI on small changes
- ❌ Premature optimization

---

## Security Guidelines

### Do

- ✅ Validate all inputs
- ✅ Use environment variables for secrets
- ✅ Sanitize user content before display
- ✅ Use HTTPS for API calls
- ✅ Log security events

### Don't

- ❌ Store secrets in code
- ❌ Trust user input
- ❌ Expose internal errors to users
- ❌ Log sensitive data
- ❌ Use eval() or equivalent

---

## Documentation

### What to Document

- **Public APIs:** All parameters, returns, exceptions
- **Complex Logic:** Why, not what
- **Configuration:** All options explained
- **Modules:** Purpose and responsibilities

### What Not to Document

- **Obvious Code:** `i++  # increment i`
- **Getters/Setters:** Self-explanatory
- **Tests:** Code should be clear enough

---

## Conclusion

These standards ensure:
- **Consistency** across the codebase
- **Maintainability** for future development
- **Quality** that scales with the project
- **Collaboration** between contributors

**Follow these standards. No exceptions without good reason.**
