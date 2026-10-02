"""Chat API endpoints with memory and safe local tool routing."""

import asyncio
import json
import re
from pathlib import Path
from typing import AsyncGenerator, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core import LLMError, get_logger, get_settings
from app.models import ChatRequest, ChatResponse, MessageRole, StreamChunk
from app.services.chat.conversation import conversation_manager
from app.services.llm.factory import create_llm_provider
from app.services.memory import get_memory_store
from app.services.memory.preferences import schedule_preference_extraction
from app.services.tools import registry
from app.services.tools.audit import record_tool_event
from app.services.tools.intent import ToolIntent, route_intent

logger = get_logger("api.chat")
router = APIRouter()


# Path from backend/app/api/v1/chat.py to repo_root/prompts/elysia.txt.
SYSTEM_PROMPT_PATH = Path(__file__).parents[4] / "prompts" / "elysia.txt"
try:
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as prompt_file:
        SYSTEM_PROMPT = prompt_file.read()
except FileNotFoundError:
    logger.warning("System prompt not found at %s, using default", SYSTEM_PROMPT_PATH)
    SYSTEM_PROMPT = (
        "You are Elysia, a concise and honest local AI assistant. "
        "Answer directly in natural spoken sentences."
    )


def _tool_result_dict(result: Any) -> dict[str, Any]:
    """Convert a ToolExecutionResult into a JSON-safe response object."""
    return {
        "status": result.status,
        "tool_name": result.tool_name,
        "result": result.result,
        "error": result.error,
        "confirmation_required": result.confirmation_required,
        "confirmation_message": result.confirmation_message,
        "metadata": result.metadata,
    }


def _bounded_tool_text(value: Any, limit: int = 700) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


_REALTIME_UNSUPPORTED = re.compile(
    r"\b(current|right now|latest|today|tonight|live|real[- ]?time)\b.*\b(weather|temperature|forecast|stock|price|score|news|president|traffic|exchange rate)\b|\b(weather|temperature|forecast|stock|price|score|news|traffic|exchange rate)\b.*\b(current|right now|latest|today|tonight|live|real[- ]?time)\b",
    re.IGNORECASE,
)


def _unsupported_realtime_response(message: str) -> str | None:
    if _REALTIME_UNSUPPORTED.search(message):
        return "I cannot verify that live information locally, so I will not guess."
    return None


def _tool_response_text(result: Any) -> str:
    """Create a concise spoken response for a tool result."""
    if result.status == "confirmation_required":
        return result.confirmation_message or "Please confirm that I should run this action."
    if result.status == "failed":
        return result.error or "I could not complete that action."
    if result.tool_name == "get_current_time":
        return f"The current local time is {result.result}."
    if result.tool_name == "get_system_info":
        return "I retrieved your system information."
    if result.tool_name == "launch_application":
        application = (result.result or {}).get("application", "the application")
        return f"I launched {application}."
    if result.tool_name in {"get_world_news", "get_world_finance_news"}:
        articles = result.result or []
        titles = [
            _bounded_tool_text(article.get("title", ""), 180)
            for article in articles
            if isinstance(article, dict) and article.get("title")
        ][:3]
        if not titles:
            return "I could not retrieve usable current headlines."
        return "Current headlines: " + "; ".join(titles)
    if result.tool_name == "search_local_files":
        count = len((result.result or {}).get("matches", []))
        return f"I found {count} matching local files."
    if result.tool_name == "summarize_local_document":
        return _bounded_tool_text((result.result or {}).get("summary", "I summarized the document."))
    if result.tool_name == "draft_text":
        return _bounded_tool_text((result.result or {}).get("draft", "I created the draft."))
    if result.tool_name == "create_reminder":
        return (result.result or {}).get("message", "I created the reminder.")
    if result.tool_name == "list_reminders":
        count = (result.result or {}).get("count", 0)
        return f"You have {count} pending reminders."
    if result.tool_name == "cancel_reminder":
        return "I cancelled the reminder."
    if result.tool_name == "list_windows":
        return f"I found {(result.result or {}).get('count', 0)} visible windows."
    if result.tool_name == "get_active_window":
        title = ((result.result or {}).get("window") or {}).get("title", "the active window")
        return f"The active window is {title}."
    if result.tool_name == "network_status":
        return "The network status is available." if (result.result or {}).get("available") else "The network status is unavailable."
    if result.tool_name == "read_clipboard":
        return "I read the current clipboard."
    if result.tool_name == "read_desktop_file":
        return "I read the local file."
    if result.tool_name == "write_desktop_file":
        return "I wrote the local file."
    if result.tool_name == "delete_desktop_file":
        return "I moved the file to reversible trash."
    if result.tool_name == "restore_desktop_file":
        return "I restored the local file."
    if result.tool_name == "get_system_volume":
        payload = result.result or {}
        return f"The volume is {payload.get('volume_percent', 0)} percent." + (" It is muted." if payload.get("muted") else "")
    if result.tool_name == "set_system_volume":
        return f"I set the volume to {(result.result or {}).get('volume_percent', 0)} percent."
    if result.tool_name == "set_system_mute":
        return "I muted the computer." if (result.result or {}).get("muted") else "I unmuted the computer."
    if result.tool_name == "get_display_brightness":
        return f"The display brightness is {(result.result or {}).get('brightness_percent', 0)} percent."
    if result.tool_name == "set_display_brightness":
        return f"I set the display brightness to {(result.result or {}).get('brightness_percent', 0)} percent."
    if result.tool_name == "open_windows_settings":
        return f"I opened {(result.result or {}).get('page', 'Windows Settings')} settings."
    if result.tool_name == "index_code_repository":
        return f"I indexed {(result.result or {}).get('file_count', 0)} source files."
    if result.tool_name == "analyze_code_repository":
        payload = result.result or {}
        return f"The project contains {payload.get('file_count', 0)} source files across {len(payload.get('languages', {}))} languages."
    if result.tool_name == "search_code_repository":
        return f"I found {len((result.result or {}).get('matches', []))} code matches."
    return f"I completed {result.tool_name}."


async def _run_tool_intent(
    intent: ToolIntent,
    request: ChatRequest,
    conv_id: UUID,
) -> tuple[str, dict[str, Any]]:
    """Execute a routed intent and persist a concise action result in history."""
    result = await registry.execute(
        intent.tool_name,
        intent.arguments,
        confirmed=request.confirm_tool,
    )
    result_dict = _tool_result_dict(result)
    record_tool_event(
        tool_name=intent.tool_name,
        status=result.status,
        arguments=intent.arguments,
        result=result_dict,
    )
    response_text = _tool_response_text(result)
    conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, response_text)
    schedule_preference_extraction(request.message)
    return response_text, result_dict


@router.post("/")
async def chat(request: ChatRequest):
    """Send a message, route safe commands, or generate a streamed LLM response."""
    settings = get_settings()

    conversation = conversation_manager.get_or_create(request.conversation_id)
    conv_id = conversation.conversation_id
    conversation_manager.add_message(conv_id, MessageRole.USER, request.message)

    # Route high-confidence commands before creating an LLM request.
    intent = route_intent(request.message)
    if intent is not None:
        response_text, result_dict = await _run_tool_intent(intent, request, conv_id)
        if request.stream:

            async def generate_tool() -> AsyncGenerator[str, None]:
                tool_chunk = StreamChunk(
                    type="tool",
                    content=response_text,
                    tool_result=result_dict,
                )
                yield f"data: {tool_chunk.model_dump_json()}\n\n"
                done = StreamChunk(type="done", conversation_id=conv_id)
                yield f"data: {done.model_dump_json()}\n\n"

            return StreamingResponse(generate_tool(), media_type="text/event-stream")

        return ChatResponse(
            response=response_text,
            conversation_id=conv_id,
            model="local-tool-router",
            tool_result=result_dict,
        )

    realtime_response = _unsupported_realtime_response(request.message)
    if realtime_response is not None:
        conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, realtime_response)
        schedule_preference_extraction(request.message)
        return ChatResponse(
            response=realtime_response,
            conversation_id=conv_id,
            model="local-safety-guard",
        )

    provider_name = request.provider or settings.DEFAULT_LLM_PROVIDER
    try:
        llm = create_llm_provider(provider_name)
    except Exception as exc:
        logger.error("Failed to create LLM provider: %s", exc)
        raise HTTPException(status_code=500, detail=f"Provider error: {exc}") from exc

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if settings.ENABLE_MEMORY:
        memories = await asyncio.to_thread(
            get_memory_store().search,
            request.message,
            "default",
            settings.MEMORY_MAX_RESULTS,
        )
        if memories:
            memory_text = "\n".join(f"- {memory.content}" for memory in memories)
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Relevant user memories. Use only when useful and never invent details:\n"
                        + memory_text
                    ),
                }
            )

    # Keep the prompt bounded for small local models.
    recent_messages = conversation.messages[-settings.MAX_CONTEXT_MESSAGES :]
    for message in recent_messages:
        messages.append({"role": message.role.value, "content": message.content})

    if request.stream:

        async def generate() -> AsyncGenerator[str, None]:
            try:
                full_response = ""
                async for token in llm.generate(
                    messages,
                    temperature=request.temperature if request.temperature is not None else 0.2,
                ):
                    full_response += token
                    chunk = StreamChunk(type="token", content=token)
                    yield f"data: {chunk.model_dump_json()}\n\n"

                conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, full_response)
                schedule_preference_extraction(request.message)
                done = StreamChunk(type="done", conversation_id=conv_id)
                yield f"data: {done.model_dump_json()}\n\n"
            except LLMError as exc:
                logger.error("LLM error during streaming: %s", exc)
                error = StreamChunk(type="error", error=str(exc))
                yield f"data: {error.model_dump_json()}\n\n"
            except Exception as exc:
                logger.error("Unexpected error during streaming: %s", exc)
                error = StreamChunk(type="error", error="An unexpected error occurred")
                yield f"data: {error.model_dump_json()}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    try:
        full_response = ""
        async for token in llm.generate(
            messages,
            temperature=request.temperature if request.temperature is not None else 0.2,
        ):
            full_response += token

        conversation_manager.add_message(conv_id, MessageRole.ASSISTANT, full_response)
        schedule_preference_extraction(request.message)
        return ChatResponse(
            response=full_response,
            conversation_id=conv_id,
            model=request.model or settings.DEFAULT_LLM_MODEL,
        )
    except LLMError as exc:
        logger.error("LLM error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        raise HTTPException(status_code=500, detail="An unexpected error occurred") from exc


@router.get("/history/{conversation_id}")
async def get_history(conversation_id: UUID):
    """Return a conversation's current in-memory history."""
    history = conversation_manager.get_history(conversation_id)
    if not history:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return history


@router.delete("/history/{conversation_id}")
async def clear_history(conversation_id: UUID):
    """Clear a conversation's current in-memory history."""
    conversation_manager.clear(conversation_id)
    return {"status": "cleared", "conversation_id": str(conversation_id)}
