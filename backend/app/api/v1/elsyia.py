"""Elsyia API — the assistant's voice/text loop and integrations.

Endpoints:
- POST /elsyia/turn      one voice turn: audio in -> transcript + reply + actions
- POST /elsyia/ask       one text turn (same loop, no STT)
- GET  /elsyia/status    loop health: STT/LLM/TTS readiness, OAuth state, latency
- POST /elsyia/gmail/connect     start Google sign-in for Gmail (opens browser)
- GET  /elsyia/gmail/status      Gmail authorisation state
- GET  /elsyia/gmail/unread      unread inbox (needs Gmail connected)
- POST /elsyia/calendar/connect  start Google sign-in for Calendar
- GET  /elsyia/calendar/status   Calendar authorisation state
- GET  /elsyia/calendar/today    today's agenda (needs Calendar connected)
- POST /elsyia/agent             agent mode: plan + execute a multi-step command
- POST /elsyia/agent/{id}/confirm  resume a plan paused for confirmation
- POST /elsyia/agent/{id}/cancel   cancel a running/paused plan
- GET  /elsyia/agent/{id}        current state of a plan
- GET  /elsyia/agent/status      agent-mode health: planner, caps, active plans
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core import TTSError, get_logger, get_settings
from app.services.elsyia.agent import get_agent_runner
from app.services.elsyia.calendar import CalendarClient, calendar_oauth
from app.services.elsyia.gmail import GmailClient, gmail_oauth
from app.services.elsyia.loop import get_elsyia_loop
from app.services.elsyia.persona import ELSYIA_NAME
from app.services.elsyia.voice_picker import (
    PREVIEW_TEXT,
    VoiceNotAvailable,
    download_voice_async,
    list_voices,
    preview_wav,
    resolve_active_voice,
    select_voice,
)
from app.services.elsyia.wakeword import WakeWordUnavailable, get_wakeword_service
from app.services.elsyia.mcp_client import get_mcp_manager
from app.services.elsyia.see import SeeUnavailable, get_see_service
from app.services.llm.factory import get_llm_provider
from app.services.voice.factory import get_stt_provider, get_tts_provider

logger = get_logger("api.elsyia")
router = APIRouter()


class ElsyiaAskRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = None
    confirmed: list[str] = Field(default_factory=list)


class ElsyiaAction(BaseModel):
    tool: str
    status: str
    confirmation_required: bool = False
    confirmation_message: str | None = None
    error: str | None = None
    result: Any | None = None


class ElsyiaTurnResponse(BaseModel):
    transcript: str
    reply: str
    conversation_id: str
    intent: str
    actions: list[ElsyiaAction]
    timings_ms: dict[str, float]


def _to_response(result) -> ElsyiaTurnResponse:
    return ElsyiaTurnResponse(
        transcript=result.transcript,
        reply=result.reply,
        conversation_id=result.conversation_id,
        intent=result.intent,
        actions=[ElsyiaAction(**a) for a in result.actions],
        timings_ms=result.timings_ms,
    )


def _conversation_uuid(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


@router.post("/turn", response_model=ElsyiaTurnResponse)
async def elsyia_turn(
    audio: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    confirmed: str | None = Form(None),
):
    """One full voice turn: mic audio -> transcript -> action/reply."""
    data = await audio.read()
    confirmed_tools = (
        {c.strip() for c in confirmed.split(",") if c.strip()} if confirmed else set()
    )
    result = await get_elsyia_loop().handle_voice(
        data,
        conversation_id=_conversation_uuid(conversation_id),
        confirmed=confirmed_tools,
    )
    return _to_response(result)


@router.post("/ask", response_model=ElsyiaTurnResponse)
async def elsyia_ask(request: ElsyiaAskRequest):
    """One text turn through the same Elsyia loop (no audio)."""
    result = await get_elsyia_loop().handle_text(
        request.message,
        conversation_id=_conversation_uuid(request.conversation_id),
        confirmed=set(request.confirmed),
    )
    return _to_response(result)


@router.get("/status")
async def elsyia_status() -> dict[str, Any]:
    """Health of the whole voice loop: STT, LLM, TTS, OAuth, tools."""
    settings = get_settings()
    status: dict[str, Any] = {
        "assistant": ELSYIA_NAME,
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
                         "voice": resolve_active_voice()}
    except Exception as exc:  # noqa: BLE001
        status["tts"] = {"ready": False, "error": str(exc)}
    status["wakeword"] = get_wakeword_service().status()
    status["mcp"] = get_mcp_manager().summary()
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
    summons the Elsyia overlay when a wake event arrives.
    """
    return get_wakeword_service().take_event() or {"wake": False}


@router.post("/wakeword/pause")
async def wakeword_pause() -> dict[str, Any]:
    """Suspend scoring while a Elsyia turn runs (so Elsyia's reply can't re-trigger)."""
    get_wakeword_service().pause()
    return get_wakeword_service().status()


@router.post("/wakeword/resume")
async def wakeword_resume() -> dict[str, Any]:
    """Resume scoring after a Elsyia turn finishes."""
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
async def elsyia_dictate(audio: UploadFile = File(...)):
    """One dictation pass: mic audio -> transcript -> cleaned text.

    Stays silent — this never triggers Elsyia's spoken reply loop. The caller
    pauses the wake-word listener while dictating.
    """
    import time as _time

    from app.services.elsyia.dictation import cleanup_transcript

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
async def elsyia_dictate_cleanup(request: DictateCleanupRequest) -> dict[str, str]:
    """Run just the Ollama cleanup pass over already-known text."""
    from app.services.elsyia.dictation import cleanup_transcript

    return {"cleaned": await cleanup_transcript(request.text)}


@router.post("/dictate/type")
async def elsyia_dictate_type(request: DictateTypeRequest) -> dict[str, Any]:
    """Type text into the currently focused application (pynput).

    The caller hides the overlay first so focus is back in the target app.
    """
    from app.services.elsyia.dictation import DictationUnavailable, type_text_async

    try:
        chars = await type_text_async(request.text)
    except DictationUnavailable as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail=str(exc))
    return {"typed_chars": chars}


@router.get("/dictation/status")
async def elsyia_dictation_status() -> dict[str, Any]:
    """Dictation capability report: hotkey, confirm setting, typing support."""
    from app.services.elsyia.dictation import dictation_status

    return dictation_status()


# --- Agent mode ("say it and it's done" multi-step chaining) ---


class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    confirmed: list[str] = Field(default_factory=list)
    stream: bool = False


class AgentConfirmRequest(BaseModel):
    confirmed: list[str] = Field(default_factory=list)
    user_input: str | None = Field(
        default=None,
        description="Answer for a plan paused with ask_user (awaiting_input).",
    )
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
    "plan_completed", "plan_failed", "awaiting_confirmation", "awaiting_input", "no_plan",
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
async def elsyia_agent_status() -> dict[str, Any]:
    """Agent-mode health: planner readiness, step caps, active plans."""
    return get_agent_runner().status()


@router.get("/agent/{plan_id}")
async def elsyia_agent_plan(plan_id: str) -> dict[str, Any]:
    """Current state of one agent plan (for polling or recovery)."""
    from fastapi import HTTPException

    plan = get_agent_runner().get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Unknown or expired plan.")
    return plan.to_dict()


@router.post("/agent/{plan_id}/cancel")
async def elsyia_agent_cancel(plan_id: str) -> dict[str, bool]:
    """Cancel a running or confirmation-paused plan."""
    return {"cancelled": get_agent_runner().cancel_plan(plan_id)}


@router.post("/agent", response_model=AgentRunResponse)
async def elsyia_agent_run(request: AgentRunRequest):
    """Plan and execute a multi-step command.

    Pass stream=true for server-sent events with live per-step progress
    (plan_created, step_started, step_completed, awaiting_confirmation,
    plan_completed, plan_failed). Destructive steps pause for confirmation;
    resume with POST /elsyia/agent/{plan_id}/confirm.
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
async def elsyia_agent_confirm(plan_id: str, request: AgentConfirmRequest):
    """Resume a confirmation- or input-paused plan.

    Pass {"user_input": "..."} to answer a plan paused with ask_user.
    """
    from fastapi import HTTPException

    runner = get_agent_runner()
    if runner.get_plan(plan_id) is None:
        raise HTTPException(status_code=404, detail="Unknown or expired plan.")
    confirmed = {c.strip() for c in request.confirmed if c.strip()}
    if request.stream:
        async def _resume(emit) -> None:
            plan = await runner.confirm_plan(
                plan_id, confirmed, user_input=request.user_input,
                event_sink=emit,
            )
            if plan is None:
                await emit({
                    "type": "no_plan",
                    "reply": "That plan is no longer awaiting confirmation.",
                })

        return StreamingResponse(_agent_sse(_resume), media_type="text/event-stream")
    plan = await runner.confirm_plan(
        plan_id, confirmed, user_input=request.user_input
    )
    if plan is None:
        raise HTTPException(
            status_code=409, detail="Plan is not awaiting confirmation."
        )
    return _agent_to_response(plan)


# --- MCP (Model Context Protocol): community integrations ---


@router.get("/mcp/status")
async def mcp_status() -> dict[str, Any]:
    """Per-server MCP status: transport, availability, tool counts, errors."""
    return get_mcp_manager().status()


@router.post("/mcp/refresh")
async def mcp_refresh() -> dict[str, Any]:
    """Reconnect all configured MCP servers (picks up config edits)."""
    await get_mcp_manager().refresh()
    return get_mcp_manager().status()


# --- Screen-aware mode ("circle anything, then just ask") ---


class ElsyiaSeeAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    capture_id: str | None = None


@router.get("/see/status")
async def elsyia_see_status() -> dict[str, Any]:
    """Vision pipeline health: model, Ollama, and whether a capture exists."""
    return await get_see_service().status()


@router.post("/see/capture")
async def elsyia_see_capture(file: UploadFile = File(...)) -> dict[str, Any]:
    """Store an explicit region capture.

    Called by the Electron shell right after the user's region select.
    This is the ONLY endpoint that creates a capture — Elsyia never
    screenshots on its own.
    """
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        return {"ok": False, "error": "Capture too large (8 MB limit)."}
    try:
        stored = get_see_service().store_capture(data)
    except SeeUnavailable as exc:
        return {"ok": False, "error": str(exc)}
    status = await get_see_service().status()
    return {"ok": True, **stored, "model_available": status["model_available"]}


@router.post("/see")
async def elsyia_see_ask(request: ElsyiaSeeAskRequest) -> dict[str, Any]:
    """Ask a question about the current explicit screen capture.

    Always returns 200 with an `ok` flag so the overlay can speak the
    outcome naturally either way.
    """
    try:
        result = await get_see_service().answer(
            request.question, capture_id=request.capture_id
        )
    except SeeUnavailable as exc:
        return {"ok": False, "answer": str(exc), "timings_ms": {"total_ms": 0}}
    return {"ok": True, **result}


# --- Voice picker (Elsyia's speaking voice, Jarvis-style) ---


class VoiceSelectRequest(BaseModel):
    voice_id: str = Field(..., min_length=1, max_length=80)


class VoicePreviewRequest(BaseModel):
    voice_id: str = Field(..., min_length=1, max_length=80)
    text: str | None = Field(default=None, max_length=400)


class VoiceDownloadRequest(BaseModel):
    voice_id: str = Field(..., min_length=1, max_length=80)


@router.get("/voice/list")
async def elsyia_voice_list() -> dict[str, Any]:
    """All known Piper voices: installed ones, downloadable ones, active one."""
    return list_voices()


@router.post("/voice/select")
async def elsyia_voice_select(request: VoiceSelectRequest) -> dict[str, Any]:
    """Switch Elsyia's speaking voice. Hot — no restart needed.

    The voice must already be downloaded (see POST /elsyia/voice/download).
    """
    try:
        active = select_voice(request.voice_id)
    except VoiceNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    # Hot-swap the cached provider so the next utterance uses the new voice.
    from app.services.voice.factory import set_tts_voice
    set_tts_voice(active)
    return {"ok": True, "active": active}


@router.post("/voice/preview")
async def elsyia_voice_preview(request: VoicePreviewRequest) -> StreamingResponse:
    """Hear a sample line in a voice WITHOUT changing the active voice."""
    text = (request.text or PREVIEW_TEXT).strip() or PREVIEW_TEXT
    if len(text) > 400:
        text = text[:400]
    try:
        wav = await preview_wav(request.voice_id, text)
    except VoiceNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except TTSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    async def generate():
        yield wav

    return StreamingResponse(generate(), media_type="audio/wav")


@router.post("/voice/download")
async def elsyia_voice_download(request: VoiceDownloadRequest) -> StreamingResponse:
    """Download a Piper voice (explicit only). Streams SSE progress events.

    Events: ``progress`` {file, downloaded, total}, then ``done`` {voice}
    or ``error`` {error}.
    """
    from app.services.elsyia.voice_picker import is_valid_voice_id, installed_voices

    voice_id = request.voice_id.strip()
    if not is_valid_voice_id(voice_id):
        raise HTTPException(status_code=400,
                            detail=f"'{request.voice_id}' is not a Piper voice id.")
    if voice_id in installed_voices():
        raise HTTPException(status_code=409,
                            detail=f"Voice '{voice_id}' is already downloaded.")

    async def events():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        finished = asyncio.Event()
        error: list = []

        def progress_cb(downloaded: int, total: int | None, filename: str) -> None:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"file": filename, "downloaded": downloaded, "total": total},
            )

        async def run() -> None:
            try:
                await download_voice_async(voice_id, progress_cb=progress_cb)
            except Exception as exc:  # noqa: BLE001
                error.append(str(exc))
            finally:
                finished.set()

        task = asyncio.create_task(run())
        while not finished.is_set() or not queue.empty():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            yield f"event: progress\ndata: {json.dumps(item)}\n\n"
        await task
        if error:
            yield f"event: error\ndata: {json.dumps({'error': error[0]})}\n\n"
        else:
            yield f"event: done\ndata: {json.dumps({'voice': voice_id})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
