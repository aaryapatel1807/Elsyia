"""Bounded local goal decomposition for Phase 8 planning."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.core import get_settings
from app.services.llm.factory import get_llm_provider
from app.services.planning.manager import PlanError, PlanTask


def _fallback(goal: str) -> list[PlanTask]:
    """Create a transparent safe sequential draft when the local model is unavailable."""
    parts = [part.strip(" .") for part in re.split(r"\s*(?:;|\band then\b|\bthen\b)\s*", goal, flags=re.I) if part.strip()]
    if len(parts) == 1:
        parts = [f"Clarify the goal and identify local inputs: {goal}", f"Prepare a bounded local result for: {goal}"]
    tasks: list[PlanTask] = []
    previous: str | None = None
    for index, part in enumerate(parts[: get_settings().PLAN_MAX_DECOMPOSED_TASKS], start=1):
        task_id = f"task_{index}"
        tasks.append(
            PlanTask(
                id=task_id,
                title=part[: get_settings().PLAN_MAX_TEXT_CHARS],
                description="Drafted locally; inspect and approve before execution.",
                dependencies=[previous] if previous else [],
                action_class="analysis",
                reasoning_summary="Deterministic fallback decomposition; no side effect assigned.",
            )
        )
        previous = task_id
    return tasks


async def decompose_goal(goal: str) -> tuple[list[PlanTask], str]:
    """Ask only the configured local Ollama provider for a bounded draft."""
    settings = get_settings()
    if not settings.PLAN_DECOMPOSITION_ENABLED:
        raise PlanError("Local goal decomposition is disabled.")
    prompt = (
        "Decompose this goal into a short JSON array of safe planning tasks. "
        "Return JSON only, with objects containing id, title, description, dependencies, "
        "action_class, and reasoning_summary. Use only action_class=analysis or "
        "local_reversible; never include network, purchases, credentials, or destructive actions. "
        f"Use at most {settings.PLAN_MAX_DECOMPOSED_TASKS} tasks and keep each text field under "
        f"{settings.PLAN_MAX_TEXT_CHARS} characters. Goal: {goal}"
    )
    try:
        provider = get_llm_provider("ollama")
        chunks: list[str] = []
        async def collect() -> None:
            async for chunk in provider.generate(
                [{"role": "system", "content": "You are a strict local planning JSON generator."}, {"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=900,
            ):
                chunks.append(str(chunk))
                if sum(len(item) for item in chunks) > settings.PLAN_MAX_TEXT_CHARS * settings.PLAN_MAX_DECOMPOSED_TASKS:
                    break
        await asyncio.wait_for(collect(), timeout=settings.PLAN_DECOMPOSITION_TIMEOUT_SECONDS)
        raw = "".join(chunks).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json\n", "", 1).strip()
        decoded: Any = json.loads(raw)
        if not isinstance(decoded, list) or not decoded:
            raise ValueError("decomposition was not a non-empty array")
        tasks = [PlanTask(**item) for item in decoded[: settings.PLAN_MAX_DECOMPOSED_TASKS] if isinstance(item, dict)]
        if not tasks:
            raise ValueError("decomposition contained no task objects")
        return tasks, "Local Ollama decomposition; review and approve before execution."
    except Exception:
        return _fallback(goal), "Local model unavailable or invalid; deterministic fallback draft."
