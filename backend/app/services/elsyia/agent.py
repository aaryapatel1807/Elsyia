"""Elsyia agent mode: "say it and it's done".

Multi-step chaining on top of the deterministic single-intent fast path.
A command like "grab my flight info from Gmail, put it on my calendar,
and text Mom the details" is decomposed by the local Ollama planner into
an ordered plan against the REAL tool manifest, then executed step by
step with outputs threaded forward:

  step 1 (search_gmail) -> step 2 (read_gmail, id from step 1)
      -> step 3 (create_calendar_event, details from step 2)
      -> step 4 (message_whatsapp, details from step 2)

Design notes:
- The deterministic fast path (route_intent) always runs first. The
  planner only engages when the utterance looks multi-intent or when the
  fast path finds no single match.
- Reads proceed silently; outward/destructive steps keep the registry's
  confirmation gate — the plan pauses and resumes after Aarya confirms.
- On any step failure: stop, keep partial results, report exactly what
  succeeded and what didn't. Never silently skip.
- Plans live in an in-memory store (15-minute TTL) so a plan can pause
  for confirmation and resume via POST /elsyia/agent/{plan_id}/confirm.
- Everything is local: Ollama plans, local tools execute. No cloud.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core import get_logger, get_settings
from app.services.elsyia.loop import _describe_tool_result
from app.services.llm.factory import get_llm_provider
from app.services.tools.intent import route_intent
from app.services.tools.registry import registry

logger = get_logger("elsyia.agent")

_PLAN_TTL_S = 15 * 60

# Utterances carrying an explicit sequencing cue are multi-intent even when
# part of them happens to match a single-intent pattern.
_CHAIN_CUES_RE = re.compile(
    r"\b(and then|then|after that|followed by|and also)\b|;",
    re.IGNORECASE,
)

# Split points that may join two commands: "and", ";", "then", ",".
_SPLIT_RE = re.compile(r"\s+and\s+|\s*;\s*|\s+then\s+|,\s*", re.IGNORECASE)

# A segment starting with one of these verbs is (almost) certainly its own
# action: "find my flight AND ADD to calendar" -> two actions, but
# "remind me to buy milk AND EGGS" stays one.
_ACTION_VERBS = frozenset({
    "add", "put", "send", "text", "message", "email", "set", "create",
    "schedule", "play", "open", "remind", "search", "find", "check",
    "draft", "write", "take", "list", "show", "tell", "start", "launch",
    "summarize", "cancel", "delete", "move",
})


def looks_multi_intent(text: str) -> bool:
    """Heuristic: does this utterance ask for more than one action?"""
    text = (text or "").strip()
    if not text:
        return False
    if _CHAIN_CUES_RE.search(text):
        return True
    parts = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
    if len(parts) < 2:
        return False
    first_words = {p.split()[0].lower() for p in parts[1:] if p.split()}
    return bool(first_words & _ACTION_VERBS)


_PLACEHOLDER_RE = re.compile(r"\{\{\s*steps\.(last|\d+)\.([A-Za-z0-9_.]+)\s*\}\}")

# Argument shapes for the tools most often chained. The planner only ever
# sees real tools (validated against the registry), these hints keep its
# arguments shaped like the real signatures.
_ARG_HINTS: dict[str, str] = {
    "search_gmail": '{"query": "<gmail search>", "max_results": 5}',
    "read_gmail": '{"message_id": "<id from a search result>"}',
    "send_gmail": '{"to": "<email>", "subject": "<subject>", "body": "<body>"}',
    "check_gmail": '{"max_results": 5}',
    "calendar_today": '{}',
    "create_calendar_event": '{"title": "<title>", "start": "<ISO-8601>", "end": "", "description": "<details>"}',
    "message_whatsapp": '{"to": "<name or phone>", "text": "<message>"}',
    "take_note": '{"text": "<note>"}',
    "read_notes": '{}',
    "set_timer": '{"minutes": <number>, "label": "<optional>"}',
    "create_reminder": '{"title": "<title>", "due_at": "<ISO-8601>"}',
    "play_youtube": '{"query": "<what to play>"}',
    "ask_user": '{"question": "<what you need to know>"}',
    "open_linkedin": '{"view": "feed|jobs|search:<keywords>|profile:<name>"}',
    "search_web": '{"query": "<query>"}',
    "draft_text": '{"instruction": "<what to draft>"}',
    "get_current_time": '{}',
    "get_current_date": '{}',
    "get_weather": '{"location": "<city, optional>"}',
    "get_system_stats": '{}',
    "morning_briefing": '{"location": "<city, optional>"}',
    "see_capture": '{"question": "<what to look at in the user\'s current screen capture>"}',
    "launch_application": '{"application": "<app name>"}',
}

_DEFAULT_PLANNER_PROMPT = """You are Elsyia's action planner. Break the command into tool steps.
TOOLS:
{tool_manifest}
RULES: output STRICT JSON {"steps": [{"tool": "<name>", "args": {}, "say": "<narration>"}]} and nothing else.
Use ONLY listed tools. At most {max_steps} steps. Reads before writes.
"say" is a short present-tense narration under 8 words.
Thread outputs with {{steps.N.field}} / {{steps.last.field}} placeholders.
Single simple action or no sensible plan -> {"steps": []}.
User: "{utterance}"
"""


def load_planner_prompt() -> str:
    """Load the planner prompt from prompts/, falling back to the embedded copy."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[4] / "prompts" / "agent-planner.txt",
        Path.cwd() / "prompts" / "agent-planner.txt",
    ]
    for path in candidates:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return _DEFAULT_PLANNER_PROMPT


def build_tool_manifest() -> str:
    """Render the real registry as planner context: name, description, confirm flag, arg hints."""
    lines = []
    for tool in registry.list():
        hint = _ARG_HINTS.get(tool["name"], "")
        confirm = "needs-confirm" if tool["confirmation_required"] else "no-confirm"
        line = f"- {tool['name']} [{confirm}]: {tool['description']}"
        if hint:
            line += f" Args: {hint}"
        lines.append(line)
    return "\n".join(lines)


def _parse_plan_json(raw: str, max_steps: int) -> list[dict[str, Any]]:
    """Extract and validate planner steps. Returns [] when unusable."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    except Exception:  # noqa: BLE001 — planner output must never crash the loop
        return []
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list):
        return []
    known = {t["name"] for t in registry.list()}
    valid: list[dict[str, Any]] = []
    for item in steps[:max_steps]:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if not isinstance(tool, str) or tool not in known:
            continue
        args = item.get("args", {})
        if not isinstance(args, dict):
            continue
        say = item.get("say") or f"Running {tool}…"
        valid.append({"tool": tool, "args": args, "say": str(say)[:80]})
    return valid


async def plan_with_llm(text: str, settings: Any | None = None) -> list[dict[str, Any]]:
    """Ask the local Ollama planner to decompose text into validated steps."""
    settings = settings or get_settings()
    max_steps = settings.ELSYIA_AGENT_MAX_STEPS
    provider = get_llm_provider(settings.DEFAULT_LLM_PROVIDER)
    prompt = (
        load_planner_prompt()
        .replace("{tool_manifest}", build_tool_manifest())
        .replace("{max_steps}", str(max_steps))
        .replace("{utterance}", text.strip())
    )
    chunks: list[str] = []
    async for chunk in provider.generate(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1200,
    ):
        chunks.append(chunk)
    raw = "".join(chunks).strip()
    steps = _parse_plan_json(raw, max_steps)
    logger.info("Agent planner: %d valid steps for %r", len(steps), text[:60])
    return steps


def _lookup(completed: dict[int, Any], ref: str, path: str) -> Any:
    if ref == "last":
        if not completed:
            return None
        seq = max(completed)
    else:
        seq = int(ref)
    node = completed.get(seq)
    for part in path.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit():
            idx = int(part)
            node = node[idx] if 0 <= idx < len(node) else None
        else:
            return None
    return node


def resolve_placeholders(value: Any, completed: dict[int, Any]) -> Any:
    """Resolve {{steps.N.path}} / {{steps.last.path}} against finished steps.

    A value that IS a single placeholder keeps its native type; placeholders
    embedded in longer text are string-interpolated (missing -> "").
    """
    if isinstance(value, str):
        stripped = value.strip()
        full = _PLACEHOLDER_RE.fullmatch(stripped)
        if full:
            return _lookup(completed, full.group(1), full.group(2))

        def _sub(match: re.Match[str]) -> str:
            found = _lookup(completed, match.group(1), match.group(2))
            return "" if found is None else str(found)

        return _PLACEHOLDER_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: resolve_placeholders(v, completed) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_placeholders(v, completed) for v in value]
    return value


@dataclass
class AgentStep:
    seq: int
    tool: str
    args: dict[str, Any]
    say: str
    status: str = "pending"  # pending|running|awaiting_confirmation|awaiting_input|completed|failed|skipped
    needs_confirm: bool = False
    confirmation_message: str | None = None
    result: Any | None = None
    error: str | None = None
    timing_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tool": self.tool,
            "say": self.say,
            "status": self.status,
            "needs_confirm": self.needs_confirm,
            "confirmation_message": self.confirmation_message,
            "result": self.result,
            "error": self.error,
            "timing_ms": round(self.timing_ms, 1),
        }


@dataclass
class AgentPlan:
    plan_id: str
    message: str
    steps: list[AgentStep] = field(default_factory=list)
    status: str = "running"  # running|awaiting_confirmation|awaiting_input|completed|failed|no_plan|cancelled
    reply: str = ""
    timings_ms: dict[str, float] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    confirmed: set[str] = field(default_factory=set)

    @property
    def results(self) -> dict[int, Any]:
        return {
            s.seq: s.result for s in self.steps if s.status == "completed"
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "message": self.message,
            "status": self.status,
            "reply": self.reply,
            "steps": [s.to_dict() for s in self.steps],
            "timings_ms": {k: round(v, 1) for k, v in self.timings_ms.items()},
        }


EventSink = Callable[[dict[str, Any]], Awaitable[None]]


class AgentRunner:
    """Plans and executes multi-step tool chains with confirmation pauses."""

    def __init__(self) -> None:
        self._plans: dict[str, AgentPlan] = {}
        self._lock = asyncio.Lock()

    # --- plan store ---

    def _purge(self) -> None:
        cutoff = time.time() - _PLAN_TTL_S
        expired = [pid for pid, p in self._plans.items() if p.created_at < cutoff]
        for pid in expired:
            del self._plans[pid]

    def get_plan(self, plan_id: str) -> AgentPlan | None:
        self._purge()
        return self._plans.get(plan_id)

    def cancel_plan(self, plan_id: str) -> bool:
        plan = self.get_plan(plan_id)
        if plan is None or plan.status in ("completed", "failed", "cancelled"):
            return False
        plan.status = "cancelled"
        for step in plan.steps:
            if step.status in ("pending", "running"):
                step.status = "skipped"
        plan.reply = "Cancelled — nothing further will run."
        return True

    def active_plans(self) -> int:
        self._purge()
        return len(self._plans)

    def planner_ready(self) -> bool:
        try:
            get_llm_provider(get_settings().DEFAULT_LLM_PROVIDER)
            return True
        except Exception:  # noqa: BLE001
            return False

    def status(self) -> dict[str, Any]:
        settings = get_settings()
        return {
            "enabled": True,
            "planner_ready": self.planner_ready(),
            "planner_model": settings.DEFAULT_LLM_MODEL,
            "max_steps": settings.ELSYIA_AGENT_MAX_STEPS,
            "step_timeout_s": settings.ELSYIA_AGENT_STEP_TIMEOUT_S,
            "active_plans": self.active_plans(),
        }

    # --- planning ---

    async def _build_steps(
        self, text: str, settings: Any
    ) -> tuple[list[AgentStep], dict[str, float], str]:
        """Fast path first, planner second. Returns (steps, timings, route)."""
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        routed = route_intent(text)
        timings["nlu_ms"] = (time.perf_counter() - t0) * 1000
        if routed is not None and not looks_multi_intent(text):
            step = AgentStep(
                seq=1, tool=routed.tool_name, args=routed.arguments,
                say=f"Running {routed.tool_name}…",
            )
            return [step], timings, "fast_path"
        t1 = time.perf_counter()
        raw_steps = await plan_with_llm(text, settings)
        if not raw_steps and len(text.split()) >= 3:
            # One retry with a stricter prompt: small local models sometimes
            # ramble instead of emitting JSON on the first attempt.
            logger.info("Agent planner: empty plan, retrying once with strict prompt")
            strict = load_planner_prompt() + (
                "\nSTRICT: output ONLY the JSON object. No prose, no markdown."
            )
            chunks: list[str] = []
            provider = get_llm_provider(settings.DEFAULT_LLM_PROVIDER)
            prompt = strict.replace(
                "{tool_manifest}", build_tool_manifest()
            ).replace("{max_steps}", str(settings.ELSYIA_AGENT_MAX_STEPS)).replace(
                "{utterance}", text.strip()
            )
            try:
                async for chunk in provider.generate(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=1200,
                ):
                    chunks.append(chunk)
                raw_steps = _parse_plan_json(
                    "".join(chunks).strip(), settings.ELSYIA_AGENT_MAX_STEPS
                )
            except Exception as exc:  # noqa: BLE001 — retry is best-effort
                logger.debug("Agent planner retry failed: %s", exc)
        timings["plan_ms"] = (time.perf_counter() - t1) * 1000
        steps = [
            AgentStep(seq=i + 1, tool=s["tool"], args=s["args"], say=s["say"])
            for i, s in enumerate(raw_steps)
        ]
        return steps, timings, "planner"

    # --- execution ---

    async def _run_steps(
        self,
        plan: AgentPlan,
        settings: Any,
        emit: EventSink,
    ) -> None:
        for step in plan.steps:
            if step.status != "pending":
                continue
            # ask_user never executes: the plan pauses and waits for Aarya's
            # answer, which resumes via confirm_plan(user_input=...).
            if step.tool == "ask_user":
                question = str(
                    step.args.get("question") or "I need your input to continue."
                ).strip()
                step.status = "awaiting_input"
                step.confirmation_message = question
                plan.status = "awaiting_input"
                await emit(self._step_event("step_awaiting_input", plan, step))
                return
            step.status = "running"
            t0 = time.perf_counter()
            await emit({
                "type": "step_started", "plan_id": plan.plan_id,
                "seq": step.seq, "tool": step.tool, "say": step.say,
            })
            try:
                args = resolve_placeholders(step.args, plan.results)
                executed = await asyncio.wait_for(
                    registry.execute(
                        step.tool, args,
                        confirmed=step.tool in plan.confirmed,
                    ),
                    timeout=settings.ELSYIA_AGENT_STEP_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                step.status = "failed"
                step.error = (
                    f"Timed out after {settings.ELSYIA_AGENT_STEP_TIMEOUT_S}s."
                )
                plan.status = "failed"
                self._skip_rest(plan, step.seq)
                await emit(self._step_event("step_failed", plan, step))
                return
            except Exception as exc:  # noqa: BLE001 — executor must not die
                # One immediate retry for transient failures (network blips,
                # flaky integrations). Timeouts and tool-reported failures
                # below are NOT retried.
                logger.warning(
                    "Agent step %d (%s) failed, retrying once: %s",
                    step.seq, step.tool, exc,
                )
                try:
                    await asyncio.sleep(1.0)
                    executed = await asyncio.wait_for(
                        registry.execute(
                            step.tool, args,
                            confirmed=step.tool in plan.confirmed,
                        ),
                        timeout=settings.ELSYIA_AGENT_STEP_TIMEOUT_S,
                    )
                except Exception as retry_exc:  # noqa: BLE001
                    step.status = "failed"
                    step.error = (
                        f"Unexpected error: {type(retry_exc).__name__} "
                        f"(after 1 retry)"
                    )
                    plan.status = "failed"
                    self._skip_rest(plan, step.seq)
                    logger.exception(
                        "Agent step %d (%s) crashed", step.seq, step.tool
                    )
                    await emit(self._step_event("step_failed", plan, step))
                    return

            step.timing_ms = (time.perf_counter() - t0) * 1000
            if executed.status == "confirmation_required":
                step.status = "awaiting_confirmation"
                step.needs_confirm = True
                step.confirmation_message = executed.confirmation_message
                plan.status = "awaiting_confirmation"
                await emit(self._step_event("step_awaiting_confirmation", plan, step))
                return
            if executed.status == "failed":
                step.status = "failed"
                step.error = executed.error or "The tool reported a failure."
                plan.status = "failed"
                self._skip_rest(plan, step.seq)
                await emit(self._step_event("step_failed", plan, step))
                return
            step.status = "completed"
            step.result = executed.result
            await emit(self._step_event("step_completed", plan, step))

        plan.status = "completed"

    @staticmethod
    def _skip_rest(plan: AgentPlan, failed_seq: int) -> None:
        for step in plan.steps:
            if step.seq > failed_seq and step.status == "pending":
                step.status = "skipped"

    @staticmethod
    def _step_event(
        event_type: str, plan: AgentPlan, step: AgentStep
    ) -> dict[str, Any]:
        return {
            "type": event_type, "plan_id": plan.plan_id,
            "seq": step.seq, "tool": step.tool, "say": step.say,
            "step": step.to_dict(),
        }

    def _compose_reply(self, plan: AgentPlan) -> str:
        done = [s for s in plan.steps if s.status == "completed"]
        said = " ".join(
            _describe_tool_result(s.tool, s.result) for s in done
        ).strip()

        if plan.status == "completed":
            n = len(done)
            return f"Done — {n} step{'s' if n != 1 else ''}. {said}".strip()
        if plan.status == "awaiting_confirmation":
            step = next(
                s for s in plan.steps if s.status == "awaiting_confirmation"
            )
            return (
                f"{step.confirmation_message or 'This step needs your approval.'} "
                "Say 'yes' or tap confirm and I'll carry on with the rest."
            )
        if plan.status == "awaiting_input":
            step = next(
                (s for s in plan.steps if s.status == "awaiting_input"), None
            )
            question = (step.confirmation_message if step
                        else "I need your input to continue.")
            return f"{question} Reply and I'll carry on."
        if plan.status == "failed":
            step = next(s for s in plan.steps if s.status == "failed")
            head = (
                f"I managed {len(done)} of {len(plan.steps)} steps. "
                if done else ""
            )
            return (
                f"{head}Then I got stuck on '{step.say}': "
                f"{step.error or 'it failed.'}".strip()
            )
        if plan.status == "no_plan":
            return (
                "I couldn't break that down into steps I can actually run. "
                "Try splitting it into smaller asks."
            )
        return plan.reply or "Done."

    # --- public API ---

    async def run_text(
        self,
        text: str,
        confirmed: set[str] | None = None,
        event_sink: EventSink | None = None,
    ) -> AgentPlan:
        """Plan and execute one utterance. Streams events when event_sink is set."""
        settings = get_settings()
        t_start = time.perf_counter()
        text = (text or "").strip()

        async def emit(event: dict[str, Any]) -> None:
            if event_sink is None:
                return
            delivered = event_sink(event)
            if asyncio.iscoroutine(delivered):
                await delivered

        plan = AgentPlan(
            plan_id=uuid.uuid4().hex[:12],
            message=text,
            confirmed=set(confirmed or ()),
        )
        if not text:
            plan.status = "no_plan"
            plan.reply = "I didn't catch that."
            await emit({"type": "no_plan", "plan": plan.to_dict(),
                        "reply": plan.reply})
            return plan

        steps, timings, route = await self._build_steps(text, settings)
        plan.steps = steps
        plan.timings_ms.update(timings)

        await emit({"type": "plan_created", "plan": plan.to_dict(),
                    "route": route})
        if not steps:
            plan.status = "no_plan"
        else:
            await self._run_steps(plan, settings, emit)

        plan.reply = self._compose_reply(plan)
        plan.timings_ms["total_ms"] = (time.perf_counter() - t_start) * 1000
        async with self._lock:
            self._plans[plan.plan_id] = plan
        terminal = {
            "completed": "plan_completed",
            "failed": "plan_failed",
            "awaiting_confirmation": "awaiting_confirmation",
            "awaiting_input": "awaiting_input",
            "no_plan": "no_plan",
        }[plan.status]
        await emit({"type": terminal, "plan": plan.to_dict(),
                    "reply": plan.reply})
        logger.info(
            "Agent plan %s: route=%s status=%s steps=%d total_ms=%.0f",
            plan.plan_id, route, plan.status, len(steps),
            plan.timings_ms["total_ms"],
        )
        return plan

    async def confirm_plan(
        self,
        plan_id: str,
        confirmed: set[str],
        user_input: str | None = None,
        event_sink: EventSink | None = None,
    ) -> AgentPlan | None:
        """Resume a plan paused for confirmation or user input.

        Returns None when unknown. When the plan is awaiting_input and no
        user_input is given, the plan is returned unchanged (still waiting).
        """
        async with self._lock:
            plan = self.get_plan(plan_id)
            if plan is None or plan.status not in (
                "awaiting_confirmation", "awaiting_input"
            ):
                return None
            if plan.status == "awaiting_input":
                waiting = next(
                    (s for s in plan.steps if s.status == "awaiting_input"), None
                )
                answer = (user_input or "").strip()
                if waiting is None or not answer:
                    return plan  # still waiting for the answer
                waiting.status = "completed"
                waiting.result = {"answer": answer}
                waiting.confirmation_message = None
            else:
                plan.confirmed |= set(confirmed)
                for step in plan.steps:
                    if step.status == "awaiting_confirmation":
                        step.status = "pending"
                        step.confirmation_message = None
            plan.status = "running"

        async def emit(event: dict[str, Any]) -> None:
            if event_sink is None:
                return
            delivered = event_sink(event)
            if asyncio.iscoroutine(delivered):
                await delivered

        settings = get_settings()
        t_start = time.perf_counter()
        await emit({"type": "plan_resumed", "plan": plan.to_dict()})
        await self._run_steps(plan, settings, emit)
        plan.reply = self._compose_reply(plan)
        plan.timings_ms["total_ms"] = plan.timings_ms.get("total_ms", 0) + (
            time.perf_counter() - t_start
        ) * 1000
        terminal = {
            "completed": "plan_completed",
            "failed": "plan_failed",
            "awaiting_confirmation": "awaiting_confirmation",
            "awaiting_input": "awaiting_input",
        }[plan.status]
        await emit({"type": terminal, "plan": plan.to_dict(),
                    "reply": plan.reply})
        return plan


_agent_runner: AgentRunner | None = None


def get_agent_runner() -> AgentRunner:
    global _agent_runner
    if _agent_runner is None:
        _agent_runner = AgentRunner()
    return _agent_runner
