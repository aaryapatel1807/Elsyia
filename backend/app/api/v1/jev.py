"""Jev API — the assistant's voice/text loop and integrations.

Endpoints:
- POST /jev/turn      one voice turn: audio in -> transcript + reply + actions
- POST /jev/ask       one text turn (same loop, no STT)
- GET  /jev/status    loop health: STT/LLM/TTS readiness, OAuth state, latency
- POST /jev/gmail/connect     start Google sign-in for Gmail (opens browser)
- GET  /jev/gmail/status      Gmail authorisation state
- GET  /jev/gmail/unread      unread inbox (needs Gmail connected)
- POST /jev/calendar/connect  start Google sign-in for Calendar
- GET  /jev/calendar/status   Calendar authorisation state
- GET  /jev/calendar/today    today's agenda (needs Calendar connected)
- POST /jev/agent             agent mode: plan + execute a multi-step command
- POST /jev/agent/{id}/confirm  resume a plan paused for confirmation
- POST /jev/agent/{id}/cancel   cancel a running/paused plan
- GET  /jev/agent/{id}        current state of a plan
- GET  /jev/agent/status      agent-mode health: planner, caps, active plans
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core import get_logger, get_settings
from app.services.jev.agent import get_agent_runner
from app.services.jev.calendar import CalendarClient, calendar_oauth
from app.services.jev.gmail import GmailClient, gmail_oauth
from app.services.jev.loop import get_jev_loop
from app.services.jev.persona import JEV_NAME
from app.services.jev.wakeword import WakeWordUnavailable, get_wakeword_service
from app.services.llm.factory import get_llm_provider
from app.services.voice.factory import get_stt_provider, get_tts_provider

logger = get_logger("api.jev")
router = APIRouter()


class JevAskRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    confirmed: list[str] = Field(default_factory=list)


class JevAction(BaseModel):
    tool: str
    status: str
    confirmation_required: bool = False
    confirmation_message: str | None = None
    error: str | None = None
    result: Any | None = None


class JevTurnResponse(BaseModel):
    transcript: str
    reply: str
    conversation_id: str
    intent: str
    actions: list[JevAction]
    timings_ms: dict[str, float]


def _to_response(result) -> JevTurnResponse:
    return JevTurnResponse(
        transcript=result.transcript,
        reply=result.reply,
        conversation_id=result.conversation_id,
        intent=result.intent,
        actions=[JevAction(**a) for a in result.actions],
        timings_ms=result.timings_ms,
    )


def _conversation_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


@router.post("/turn", response_model=JevTurnResponse)
async def jev_turn(
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    confirmed: str | None = Form(None),
):
    """One full voice turn: mic audio -> transcript -> action/reply."""
    data = await audio.read()
    confirmed_tools = (
        {c.strip() for c in confirmed.split(",") if c.strip()} if confirmed else set()
    )
    result = await get_jev_loop().handle_voice(
        data,
        conversation_id=_conversation_uuid(conversation_id),
        confirmed=confirmed_tools,
    )
    return _to_response(result)


@router.post("/ask", response_model=JevTurnResponse)
async def jev_ask(request: JevAskRequest):
    """One text turn through the same Jev loop (no audio)."""
    result = await get_jev_loop().handle_text(
        request.message,
        conversation_id=_conversation_uuid(request.conversation_id),
        confirmed=set(request.confirmed),
    )
    return _to_response(result)


@router.get("/status")
async def jev_status() -> dict[str, Any]:
    """Health of the whole voice loop: STT, LLM, TTS, OAuth, tools."""
    settings = get_settings()
    status: dict[str, Any] = {
        "assistant": JEV_NAME,
        "stt": {"ready": False},
        "llm": {"ready": False},
        "tts": {"ready": False},
        "gmail": {"connected": gmail_oauth().is_authorized()},
        "calendar": {"connected": calendar_oauth().is_authorized()},
    }
    try:
        get_stt_provider(settings.DEFAULT_STT_PROVIDER)
        status["stt"] = {"ready": True, "provider": settings.DEFAULT_STT_PROVIDER,
                         "model": settings.WHISPER_MODEL}
    except Exception as exc:  # noqa: BLE001
        status["stt"] = {"ready": False, "error": str(exc)}
    try:
        get_llm_provider(settings.DEFAULT_LLM_PROVIDER)
        status["llm"] = {
            "ready": True,
            "provider": settings.DEFAULT_LLM_PROVIDER,
            "model": settings.DEFAULT_LLM_MODEL,
        }
    except Exception as exc:  # noqa: BLE001
        status["llm"] = {"ready": False, "error": str(exc)}
    try:
        get_tts_provider(settings.DEFAULT_TTS_PROVIDER)
        status["tts"] = {"ready": True, "provider": settings.DEFAULT_TTS_PROVIDER,
                         "voice": settings.PIPER_VOICE}
    except Exception as exc:  # noqa: BLE001
        status["tts"] = {"ready": False, "error": str(exc)}
    status["wakeword"] = get_wakeword_service().status()
    return status


# --- Wake word (hands-free summoning) ---


@router.get("/wakeword/status")
async def wakeword_status() -> dict[str, Any]:
    """Wake-word listener state: enabled, listening, model, availability."""
    return get_wakeword_service().status()


@router.post("/wakeword/enable")
async def wakeword_enable() -> dict[str, Any]:
    """Turn the always-on listener on (explicit opt-in). 503 if unavailable."""
    from fastapi import HTTPException

    try:
        return get_wakeword_service().set_enabled(True)
    except WakeWordUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/wakeword/disable")
async def wakeword_disable() -> dict[str, Any]:
    """Turn the always-on listener off."""
    return get_wakeword_service().set_enabled(False)


@router.get("/wakeword/event")
async def wakeword_event() -> dict[str, Any]:
    """Poll for a wake event. Returns and clears it; {"wake": false} otherwise.

    The Electron shell polls this ~twice a second while the toggle is on and
    summons the Jev overlay when a wake event arrives.
    """
    return get_wakeword_service().take_event() or {"wake": False}


@router.post("/wakeword/pause")
async def wakeword_pause() -> dict[str, Any]:
    """Suspend scoring while a Jev turn runs (so Jev's reply can't re-trigger)."""
    get_wakeword_service().pause()
    return get_wakeword_service().status()


@router.post("/wakeword/resume")
async def wakeword_resume() -> dict[str, Any]:
    """Resume scoring after a Jev turn finishes."""
    get_wakeword_service().resume()
    return get_wakeword_service().status()


# --- Gmail ---


@router.post("/gmail/connect")
async def gmail_connect() -> dict[str, str]:
    """Start the one-time Google sign-in for Gmail (opens Aarya's browser)."""
    oauth = gmail_oauth()
    if oauth.is_authorized():
        return {"status": "already_connected"}
    await oauth.authorize_interactive()
    return {"status": "connected"}


@router.get("/gmail/status")
async def gmail_status() -> dict[str, bool]:
    return {"connected": gmail_oauth().is_authorized()}


@router.get("/gmail/unread")
async def gmail_unread(max_results: int = 5) -> dict[str, Any]:
    messages = await GmailClient().list_unread(max_results=min(max_results, 10))
    return {"unread": messages, "count": len(messages)}


# --- Calendar ---


@router.post("/calendar/connect")
async def calendar_connect() -> dict[str, str]:
    """Start the one-time Google sign-in for Calendar (opens Aarya's browser)."""
    oauth = calendar_oauth()
    if oauth.is_authorized():
        return {"status": "already_connected"}
    await oauth.authorize_interactive()
    return {"status": "connected"}


@router.get("/calendar/status")
async def calendar_status() -> dict[str, bool]:
    return {"connected": calendar_oauth().is_authorized()}


@router.get("/calendar/today")
async def calendar_today() -> dict[str, Any]:
    events = await CalendarClient().today()
    return {"events": events, "count": len(events)}


# --- Dictation mode (say it, it types) ---


class DictateResponse(BaseModel):
    transcript: str
    cleaned: str
    timings_ms: dict[str, float]


class DictateCleanupRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class DictateTypeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)


@router.post("/dictate", response_model=DictateResponse)
async def jev_dictate(audio: UploadFile = File(...)):
    """One dictation pass: mic audio -> transcript -> cleaned text.

    Stays silent — this never triggers Jev's spoken reply loop. The caller
    pauses the wake-word listener while dictating.
    """
    import time as _time

    from app.services.jev.dictation import cleanup_transcript

    data = await audio.read()
    timings: dict[str, float] = {}
    t0 = _time.perf_counter()
    settings = get_settings()
    stt = get_stt_provider(settings.DEFAULT_STT_PROVIDER)
    transcript = await stt.transcribe(data)
    timings["stt_ms"] = (_time.perf_counter() - t0) * 1000
    t1 = _time.perf_counter()
    cleaned = await cleanup_transcript(transcript, settings)
    timings["cleanup_ms"] = (_time.perf_counter() - t1) * 1000
    timings["total_ms"] = (_time.perf_counter() - t0) * 1000
    logger.info(f"Dictation: {len(transcript)} chars transcribed, {len(cleaned)} cleaned")
    return DictateResponse(transcript=transcript, cleaned=cleaned, timings_ms=timings)


@router.post("/dictate/cleanup")
async def jev_dictate_cleanup(request: DictateCleanupRequest) -> dict[str, str]:
    """Run just the Ollama cleanup pass over already-known text."""
    from app.services.jev.dictation import cleanup_transcript

    return {"cleaned": await cleanup_transcript(request.text)}


@router.post("/dictate/type")
async def jev_dictate_type(request: DictateTypeRequest) -> dict[str, Any]:
    """Type text into the currently focused application (pynput).

    The caller hides the overlay first so focus is back in the target app.
    """
    from app.services.jev.dictation import DictationUnavailable, type_text_async

    try:
        chars = await type_text_async(request.text)
    except DictationUnavailable as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=str(exc))
    return {"typed_chars": chars}


@router.get("/dictation/status")
async def jev_dictation_status() -> dict[str, Any]:
    """Dictation capability report: hotkey, confirm setting, typing support."""
    from app.services.jev.dictation import dictation_status

    return dictation_status()


# --- Agent mode ("say it and it's done" multi-step chaining) ---


class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    confirmed: list[str] = Field(default_factory=list)
    stream: bool = False


class AgentConfirmRequest(BaseModel):
    confirmed: list[str] = Field(default_factory=list)
    stream: bool = False


class AgentStepModel(BaseModel):
    seq: int
    tool: str
    say: str
    status: str
    needs_confirm: bool = False
    confirmation_message: str | None = None
    result: Any | None = None
    error: str | None = None
    timing_ms: float = 0.0


class AgentRunResponse(BaseModel):
    plan_id: str
    message: str
    status: str
    reply: str
    steps: list[AgentStepModel]
    timings_ms: dict[str, float]


_TERMINAL_AGENT_EVENTS = {
    "plan_completed", "plan_failed", "awaiting_confirmation", "no_plan",
}


def _agent_to_response(plan) -> AgentRunResponse:
    return AgentRunResponse(
        plan_id=plan.plan_id,
        message=plan.message,
        status=plan.status,
        reply=plan.reply,
        steps=[AgentStepModel(**s.to_dict()) for s in plan.steps],
        timings_ms={k: round(v, 1) for k, v in plan.timings_ms.items()},
    )


async def _agent_sse(coro_factory) -> Any:
    """Yield server-sent events until the runner emits a terminal event."""
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    task = asyncio.create_task(coro_factory(emit))
    try:
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event.get("type") in _TERMINAL_AGENT_EVENTS:
                break
        await task
    finally:
        if not task.done():
            task.cancel()


@router.get("/agent/status")
async def jev_agent_status() -> dict[str, Any]:
    """Agent-mode health: planner readiness, step caps, active plans."""
    return get_agent_runner().status()


@router.get("/agent/{plan_id}")
async def jev_agent_plan(plan_id: str) -> dict[str, Any]:
    """Current state of one agent plan (for polling or recovery)."""
    from fastapi import HTTPException

    plan = get_agent_runner().get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Unknown or expired plan.")
    return plan.to_dict()


@router.post("/agent/{plan_id}/cancel")
async def jev_agent_cancel(plan_id: str) -> dict[str, bool]:
    """Cancel a running or confirmation-paused plan."""
    return {"cancelled": get_agent_runner().cancel_plan(plan_id)}


@router.post("/agent", response_model=AgentRunResponse)
async def jev_agent_run(request: AgentRunRequest):
    """Plan and execute a multi-step command.

    Pass stream=true for server-sent events with live per-step progress
    (plan_created, step_started, step_completed, awaiting_confirmation,
    plan_completed, plan_failed). Destructive steps pause for confirmation;
    resume with POST /jev/agent/{plan_id}/confirm.
    """
    runner = get_agent_runner()
    confirmed = {c.strip() for c in request.confirmed if c.strip()}
    if request.stream:
        async def _run(emit) -> None:
            await runner.run_text(
                request.message, confirmed=confirmed, event_sink=emit
            )

        return StreamingResponse(_agent_sse(_run), media_type="text/event-stream")
    plan = await runner.run_text(request.message, confirmed=confirmed)
    return _agent_to_response(plan)


@router.post("/agent/{plan_id}/confirm")
async def jev_agent_confirm(plan_id: str, request: AgentConfirmRequest):
    """Resume a confirmation-paused plan with freshly approved tools."""
    from fastapi import HTTPException

    runner = get_agent_runner()
    if runner.get_plan(plan_id) is None:
        raise HTTPException(status_code=404, detail="Unknown or expired plan.")
    confirmed = {c.strip() for c in request.confirmed if c.strip()}
    if request.stream:
        async def _resume(emit) -> None:
            plan = await runner.confirm_plan(
                plan_id, confirmed, event_sink=emit
            )
            if plan is None:
                await emit({
                    "type": "no_plan",
                    "reply": "That plan is no longer awaiting confirmation.",
                })

        return StreamingResponse(_agent_sse(_resume), media_type="text/event-stream")
    plan = await runner.confirm_plan(plan_id, confirmed)
    if plan is None:
        raise HTTPException(
            status_code=409, detail="Plan is not awaiting confirmation."
        )
    return _agent_to_response(plan)
