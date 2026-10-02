"""Jev's real-time loop: the product's core.

One turn: optional STT -> intent routing -> tool execution -> Ollama
reasoning -> spoken reply. Every stage is timed so latency can be
measured and engineered down.

Design notes:
- Deterministic intents run first (fast path, no LLM needed) for
  commands like "play X on YouTube" or "what time is it".
- Everything else goes to the local LLM with the Jev persona.
- Destructive tools keep their confirmation gate: the turn returns
  `confirmation_required` and the caller re-sends with the tool name in
  `confirmed` after Aarya approves. Jev has full permission to act —
  confirmation is a safety rail, not a capability limit.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core import get_logger, get_settings
from app.models import MessageRole
from app.services.chat.conversation import ConversationManager
from app.services.tools.intent import route_intent
from app.services.jev.persona import JEV_NAME, build_system_prompt
from app.services.llm.factory import get_llm_provider
from app.services.tools.registry import registry
from app.services.voice.factory import get_stt_provider

logger = get_logger("jev.loop")


@dataclass
class JevTurnResult:
    transcript: str = ""
    reply: str = ""
    conversation_id: str = ""
    intent: str = "none"
    actions: list[dict[str, Any]] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)


def _format_time(result: Any) -> str:
    """Format a time tool result (ISO string or dict) for speech."""
    from datetime import datetime

    raw = result.get("time") if isinstance(result, dict) else result
    try:
        parsed = datetime.fromisoformat(str(raw))
        return parsed.strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return str(raw)


def _format_date(result: Any) -> str:
    from datetime import datetime

    raw = result.get("date") if isinstance(result, dict) else result
    try:
        parsed = datetime.fromisoformat(str(raw))
        return parsed.strftime("%A, %d %B %Y")
    except (ValueError, TypeError):
        return str(raw)


def _describe_tool_result(tool_name: str, result: Any) -> str:
    """Turn a tool result into one or two short spoken sentences."""
    if tool_name == "get_current_time":
        return f"It's {_format_time(result)}."
    if tool_name == "get_current_date":
        return f"Today is {_format_date(result)}."
    if not isinstance(result, dict):
        return str(result)[:300]
    if tool_name == "play_youtube":
        if result.get("mode") == "exact_video":
            return f"Playing {result.get('title', 'your video')} on YouTube."
        return "YouTube is open with your search results."
    if tool_name == "media_control":
        action = result.get("action", "")
        words = {"play_pause": "Done.", "next": "Skipped to the next one.",
                 "previous": "Back to the previous one."}
        return words.get(action, "Done.")
    if tool_name == "message_whatsapp":
        return f"WhatsApp is open with your message to {result.get('to', '')} — press send to deliver it."
    if tool_name == "open_linkedin":
        return "LinkedIn is open."
    if tool_name == "open_spotify":
        query = result.get("query", "")
        return f"Spotify is open{' with your search' if query else ''}."
    if tool_name == "set_timer":
        return result.get("message", "Timer set.")
    if tool_name == "take_note":
        return "Noted."
    if tool_name == "read_notes":
        notes = result.get("notes", "").strip()
        return notes[-600:] if notes else "You have no notes yet."
    if tool_name == "create_reminder":
        return result.get("message", "Reminder created.")
    if tool_name == "list_reminders":
        reminders = result.get("reminders", [])
        if not reminders:
            return "You have no pending reminders."
        items = [f"{r.get('title', '')} at {r.get('due_at', '')}" for r in reminders[:5]]
        return "Your reminders: " + "; ".join(items) + "."
    if tool_name == "check_gmail":
        messages = result.get("unread", [])
        if not messages:
            return "Your inbox is clear — no unread email."
        lines = [f"{m.get('from', '')}: {m.get('subject', '')}" for m in messages[:5]]
        return f"You have {len(messages)} unread. " + "; ".join(lines) + "."
    if tool_name == "search_gmail":
        messages = result.get("results", [])
        if not messages:
            return "No emails matched that search."
        lines = [f"{m.get('from', '')}: {m.get('subject', '')}" for m in messages[:5]]
        return f"Found {len(messages)}. " + "; ".join(lines) + "."
    if tool_name == "read_gmail":
        body = (result.get("body", "") or "").strip().replace("\n", " ")
        snippet = " ".join(body.split())[:400]
        return f"From {result.get('from', '')}, subject {result.get('subject', '')}. {snippet}"
    if tool_name == "send_gmail":
        return f"Email sent to {result.get('to', '')}."
    if tool_name in {"connect_gmail", "connect_calendar"}:
        status = result.get("status", "")
        return "Already connected." if status == "already_connected" else "Connected."
    if tool_name == "calendar_today":
        events = result.get("events", [])
        if not events:
            return "Nothing on your calendar today."
        items = [f"{e.get('title', '')} at {e.get('start', '')}" for e in events[:6]]
        return "Today: " + "; ".join(items) + "."
    if tool_name == "create_calendar_event":
        return f"Added {result.get('title', 'the event')} to your calendar."
    if tool_name == "search_web":
        results = result.get("results", [])
        if not results:
            return "I couldn't find anything on that."
        first = results[0]
        return f"{first.get('title', '')}: {(first.get('snippet', '') or '')[:300]}"
    if tool_name == "summarize_document":
        return (result.get("summary", "") or "")[:500]
    if tool_name == "launch_application":
        return f"{result.get('application', 'The app')} is launching."
    # Generic fallback: brief key summary, never a raw dict dump.
    message = result.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()[:300]
    return "Done."


class JevLoop:
    """Runs Jev turns end to end with per-stage latency tracking."""

    def __init__(self) -> None:
        self._conversations = ConversationManager()
        self._llm = None

    def _llm_provider(self):
        if self._llm is None:
            settings = get_settings()
            self._llm = get_llm_provider(settings.DEFAULT_LLM_PROVIDER)
        return self._llm

    async def _run_tool(
        self, tool_name: str, arguments: dict[str, Any], confirmed: set[str]
    ) -> tuple[dict[str, Any], str]:
        """Execute one tool. Returns (action_record, spoken_reply)."""
        executed = await registry.execute(
            tool_name, arguments, confirmed=tool_name in confirmed
        )
        if executed.status == "confirmation_required":
            record = {
                "tool": tool_name,
                "status": "confirmation_required",
                "confirmation_required": True,
                "confirmation_message": executed.confirmation_message,
            }
            return record, (
                f"{executed.confirmation_message} Say 'yes' or tap confirm and I'll do it."
            )
        if executed.status == "failed":
            record = {
                "tool": tool_name,
                "status": "error",
                "error": executed.error,
                "confirmation_required": False,
            }
            return record, executed.error or "That didn't work."
        record = {
            "tool": tool_name,
            "status": "ok",
            "result": executed.result,
            "confirmation_required": False,
        }
        return record, _describe_tool_result(tool_name, executed.result)

    async def _ask_llm(self, text: str, conversation_id: UUID) -> str:
        provider = self._llm_provider()
        history = self._conversations.get_or_create(conversation_id)
        max_messages = get_settings().MAX_CONTEXT_MESSAGES
        recent = history.messages[-max_messages:]
        messages = [
            {"role": m.role.value, "content": m.content} for m in recent
        ]
        messages.append({"role": "user", "content": text})
        chunks: list[str] = []
        async for chunk in provider.generate(
            messages=messages, system_prompt=build_system_prompt()
        ):
            chunks.append(chunk)
        return "".join(chunks).strip()

    async def handle_text(
        self,
        text: str,
        conversation_id: UUID | None = None,
        confirmed: set[str] | None = None,
    ) -> JevTurnResult:
        """Run one text turn: intent -> tools -> LLM -> reply."""
        t_start = time.perf_counter()
        timings: dict[str, float] = {}
        confirmed_set = set(confirmed or ())
        text = (text or "").strip()
        if not text:
            return JevTurnResult(reply="I didn't catch that.", timings_ms=timings)

        conversation = self._conversations.get_or_create(conversation_id)
        self._conversations.add_message(
            conversation.conversation_id, MessageRole.USER, text
        )

        # Fast path: deterministic intent routing (no LLM round trip).
        t0 = time.perf_counter()
        routed = route_intent(text)
        timings["nlu_ms"] = (time.perf_counter() - t0) * 1000

        actions: list[dict[str, Any]] = []
        reply: str
        intent_name = routed.tool_name if routed else "none"

        if routed is not None:
            action, reply = await self._run_tool(
                routed.tool_name, routed.arguments, confirmed_set
            )
            actions.append(action)
            timings["tool_ms"] = (time.perf_counter() - t0) * 1000 - timings["nlu_ms"]
        else:
            # Conversational path: local LLM with the Jev persona.
            t1 = time.perf_counter()
            try:
                reply = await self._ask_llm(text, conversation.conversation_id)
            except Exception as exc:  # noqa: BLE001 — voice loop must not die
                logger.error("Jev LLM call failed: %s", exc)
                reply = (
                    "My local model isn't reachable right now. "
                    "Make sure Ollama is running and try again."
                )
            timings["llm_ms"] = (time.perf_counter() - t1) * 1000

        if not reply.strip():
            reply = "Done."
        self._conversations.add_message(
            conversation.conversation_id, MessageRole.ASSISTANT, reply
        )
        timings["total_ms"] = (time.perf_counter() - t_start) * 1000
        logger.info(
            "Jev turn: intent=%s total_ms=%.0f",
            intent_name,
            timings["total_ms"],
        )
        return JevTurnResult(
            transcript=text,
            reply=reply,
            conversation_id=str(conversation.conversation_id),
            intent=intent_name,
            actions=actions,
            timings_ms={k: round(v, 1) for k, v in timings.items()},
        )

    async def handle_voice(
        self,
        audio: bytes,
        conversation_id: UUID | None = None,
        confirmed: set[str] | None = None,
    ) -> JevTurnResult:
        """Run one voice turn: STT -> handle_text. TTS stays a client call."""
        t0 = time.perf_counter()
        stt = get_stt_provider()
        transcript = await asyncio.to_thread(stt.transcribe, audio)
        stt_ms = (time.perf_counter() - t0) * 1000
        result = await self.handle_text(text=transcript, conversation_id=conversation_id, confirmed=confirmed)
        result.transcript = transcript
        result.timings_ms["stt_ms"] = round(stt_ms, 1)
        return result


_jev_loop: JevLoop | None = None


def get_jev_loop() -> JevLoop:
    global _jev_loop
    if _jev_loop is None:
        _jev_loop = JevLoop()
    return _jev_loop
