"""
Chat Data Models

Pydantic models for chat API.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Message role enum."""
    
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """Single chat message."""
    
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "Hello, Elysia",
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }


class ChatRequest(BaseModel):
    """Chat request from client."""
    
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: Optional[UUID] = Field(default=None, description="Conversation ID")
    stream: bool = Field(default=True, description="Stream response")
    provider: Optional[Literal["ollama", "openrouter", "gemini"]] = Field(
        default=None,
        description="Override LLM provider"
    )
    model: Optional[str] = Field(default=None, description="Override model")
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="LLM temperature"
    )
    confirm_tool: bool = Field(
        default=False,
        description="Confirm a routed tool action when it requires approval"
    )

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "message": "What is the weather today?",
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "stream": True
            }
        }


class ChatResponse(BaseModel):
    """Chat response (non-streaming)."""
    
    response: str = Field(..., description="AI response")
    conversation_id: UUID = Field(..., description="Conversation ID")
    tokens_used: Optional[int] = Field(default=None, description="Tokens used")
    model: str = Field(..., description="Model used")
    tool_result: Optional[dict] = Field(default=None, description="Structured tool result")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "response": "I don't have real-time weather data yet. That capability is planned for a future phase.",
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "tokens_used": 42,
                "model": "llama3.2"
            }
        }


class StreamChunk(BaseModel):
    """Streaming response chunk."""
    
    type: Literal["token", "tool", "done", "error"] = Field(..., description="Chunk type")

    content: Optional[str] = Field(default=None, description="Content (for token type)")
    conversation_id: Optional[UUID] = Field(default=None, description="Conversation ID (for done type)")
    error: Optional[str] = Field(default=None, description="Error message (for error type)")
    tool_result: Optional[dict] = Field(default=None, description="Structured tool result")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "type": "token",
                "content": "Hello"
            }
        }


class ConversationHistory(BaseModel):
    """Conversation history."""

    conversation_id: UUID
    messages: list[Message]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Rolling summary of compacted (dropped) older turns. Prepended to the
    # LLM context so long conversations don't lose their thread.
    summary: str = ""
    
    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello",
                        "timestamp": "2025-01-15T10:30:00Z"
                    },
                    {
                        "role": "assistant",
                        "content": "Hello! How can I help you today?",
                        "timestamp": "2025-01-15T10:30:02Z"
                    }
                ],
                "created_at": "2025-01-15T10:30:00Z",
                "updated_at": "2025-01-15T10:30:02Z"
            }
        }
