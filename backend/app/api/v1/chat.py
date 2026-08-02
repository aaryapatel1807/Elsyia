"""
Chat API Endpoints

Handles chat conversations with streaming support.
"""

import json
from pathlib import Path
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
SYSTEM_PROMPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "prompts" / "elysia.txt"
try:
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    logger.warning(f"System prompt not found at {SYSTEM_PROMPT_PATH}, using default")
    SYSTEM_PROMPT = """You are Elysia, an AI Operating System. Be helpful, concise, and honest about your current Phase 1 capabilities."""


@router.post("/")
async def chat(request: ChatRequest):
    """
    Chat endpoint - send message and receive response.
    
    Supports both streaming and non-streaming modes.
    
    Args:
        request: Chat request with message and options
        
    Returns:
        Streaming or complete response based on request.stream
    """
    settings = get_settings()
    
    # Get provider
    provider_name = request.provider or settings.DEFAULT_LLM_PROVIDER
    try:
        llm = create_llm_provider(provider_name)
    except Exception as e:
        logger.error(f"Failed to create LLM provider: {e}")
        raise HTTPException(status_code=500, detail=f"Provider error: {str(e)}")
    
    # Get or create conversation
    conversation = conversation_manager.get_or_create(request.conversation_id)
    conv_id = conversation.conversation_id
    
    # Add user message
    conversation_manager.add_message(conv_id, MessageRole.USER, request.message)
    
    # Construct messages list for LLM
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation.messages:
        messages.append({"role": msg.role.value, "content": msg.content})
    
    if request.stream:
        # Streaming response using Server-Sent Events
        async def generate() -> AsyncGenerator[str, None]:
            try:
                full_response = ""
                async for token in llm.generate(
                    messages, 
                    temperature=request.temperature or 0.7
                ):
                    full_response += token
                    chunk = StreamChunk(type="token", content=token)
                    yield f"data: {chunk.model_dump_json()}\n\n"
                
                # Save assistant response
                conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, full_response)
                
                # Send done signal
                done = StreamChunk(type="done", conversation_id=conv_id)
                yield f"data: {done.model_dump_json()}\n\n"
            
            except LLMError as e:
                logger.error(f"LLM error during streaming: {e}")
                error = StreamChunk(type="error", error=str(e))
                yield f"data: {error.model_dump_json()}\n\n"
            except Exception as e:
                logger.error(f"Unexpected error during streaming: {e}")
                error = StreamChunk(type="error", error="An unexpected error occurred")
                yield f"data: {error.model_dump_json()}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")
    
    else:
        # Non-streaming response
        try:
            full_response = ""
            async for token in llm.generate(
                messages,
                temperature=request.temperature or 0.7
            ):
                full_response += token
            
            # Save assistant response
            conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, full_response)
            
            return ChatResponse(
                response=full_response,
                conversation_id=conv_id,
                model=request.model or settings.DEFAULT_LLM_MODEL,
            )
        
        except LLMError as e:
            logger.error(f"LLM error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise HTTPException(status_code=500, detail="An unexpected error occurred")


@router.get("/history/{conversation_id}")
async def get_history(conversation_id: UUID):
    """
    Get conversation history.
    
    Args:
        conversation_id: UUID of the conversation
        
    Returns:
        Conversation history with all messages
    """
    history = conversation_manager.get_history(conversation_id)
    if not history:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return history


@router.delete("/history/{conversation_id}")
async def clear_history(conversation_id: UUID):
    """
    Clear conversation history.
    
    Args:
        conversation_id: UUID of the conversation to clear
        
    Returns:
        Confirmation of deletion
    """
    conversation_manager.clear(conversation_id)
    return {"status": "cleared", "conversation_id": str(conversation_id)}
