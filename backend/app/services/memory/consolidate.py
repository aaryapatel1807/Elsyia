"""Background memory consolidation for Jev: turn conversations into durable facts.

Pattern (after mem0, adapted for local-first):
  1. EXTRACT — one LLM call pulls candidate durable facts from a turn
     (preferences, names, routines, projects). Chit-chat yields nothing.
  2. RECONCILE — each candidate is checked against existing memories:
     exact/near duplicates are dropped locally (NOOP); ambiguous overlaps
     get a small LLM ADD-vs-UPDATE decision; contradictions surface as
     UPDATE.
  3. SAVE — survivors are stored with source="observed" and approved=False,
     so they wait in the pending-review queue Jev already has. Nothing is
     auto-trusted.

Everything here is best-effort and exception-safe: consolidation must
never break or slow a voice turn. The Jev loop fires it as a background
task guarded by the JEV_MEMORY_CONSOLIDATE setting.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.core import get_logger, get_settings

logger = get_logger("memory.consolidate")

_EXTRACT_PROMPT = """You extract DURABLE facts about the user from a conversation turn.
Durable = preferences, names, routines, projects, goals, constraints.
Ignore greetings, chit-chat, one-off questions, and anything about the assistant itself.

Output STRICT JSON and nothing else:
{{"facts": [{{"content": "<one clear sentence>", "category": "<preference|identity|routine|project|goal|constraint>"}}]}}

If nothing durable was said, output {{"facts": []}}.

Turn:
{transcript}
"""

_RECONCILE_PROMPT = """An assistant memory store holds this existing memory:
EXISTING: {existing}

A new candidate fact was extracted:
CANDIDATE: {candidate}

Decide ONE: ADD (new information, keep both), UPDATE (candidate replaces/extends the existing one — reply with the merged sentence), DELETE (candidate contradicts and invalidates the existing one), NOOP (same information, keep existing).

Output STRICT JSON and nothing else:
{{"decision": "ADD|UPDATE|DELETE|NOOP", "merged": "<merged sentence, only for UPDATE>"}}
"""

_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


def _tokens(value: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(value) if len(t) > 1}


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


async def _complete_json(llm: Any, prompt: str, max_tokens: int = 600) -> dict[str, Any]:
    """Run one LLM call and parse the strict-JSON reply. {} on any failure."""
    chunks: list[str] = []
    try:
        async for chunk in llm.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=max_tokens,
        ):
            chunks.append(chunk)
    except Exception as exc:  # noqa: BLE001 — consolidation is best-effort
        logger.debug("Consolidation LLM call failed: %s", exc)
        return {}
    raw = "".join(chunks).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


async def extract_facts(transcript: str, llm: Any) -> list[dict[str, str]]:
    """Extract candidate durable facts from one conversation turn."""
    data = await _complete_json(llm, _EXTRACT_PROMPT.format(transcript=transcript[:2000]))
    facts = data.get("facts")
    if not isinstance(facts, list):
        return []
    cleaned = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        content = str(fact.get("content", "")).strip()
        category = str(fact.get("category", "general")).strip() or "general"
        if len(content) >= 10:
            cleaned.append({"content": content[:500], "category": category[:50]})
    return cleaned


async def reconcile_fact(
    candidate: dict[str, str],
    existing: list[Any],
    llm: Any,
) -> tuple[str, str | None, Any | None]:
    """Decide ADD/UPDATE/DELETE/NOOP for one candidate.

    Returns (decision, merged_content_or_None, existing_record_or_None).
    Local overlap checks handle the clear cases; the LLM only sees
    genuinely ambiguous overlaps.
    """
    best: Any | None = None
    best_score = 0.0
    for record in existing:
        score = _overlap(candidate["content"], record.content)
        if score > best_score:
            best, best_score = record, score
    if best is None or best_score < 0.35:
        return "ADD", None, None
    if best_score >= 0.75:
        return "NOOP", None, best
    data = await _complete_json(
        llm,
        _RECONCILE_PROMPT.format(existing=best.content, candidate=candidate["content"]),
        max_tokens=300,
    )
    decision = str(data.get("decision", "NOOP")).upper()
    if decision not in {"ADD", "UPDATE", "DELETE", "NOOP"}:
        decision = "NOOP"
    merged = str(data.get("merged", "")).strip() or None
    if decision == "UPDATE" and not merged:
        decision, merged = "ADD", None
    return decision, merged, best


async def consolidate_turn(
    user_text: str,
    assistant_reply: str,
    llm: Any,
    store: Any,
    scope: str = "default",
) -> list[Any]:
    """Extract, reconcile and stage durable facts from one turn.

    Returns the staged (pending-approval) memory records.
    """
    transcript = f"User: {user_text}\nAssistant: {assistant_reply}"
    facts = await extract_facts(transcript, llm)
    if not facts:
        return []
    staged = []
    for fact in facts:
        try:
            existing = store.search(fact["content"], scope=scope, limit=5)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Consolidation search failed: %s", exc)
            existing = []
        decision, merged, record = await reconcile_fact(fact, existing, llm)
        try:
            if decision == "ADD":
                staged.append(
                    store.save(
                        fact["content"], scope=scope, category=fact["category"],
                        source="observed", approved=False,
                    )
                )
            elif decision == "UPDATE" and record is not None:
                store.delete(record.id, scope=scope)
                staged.append(
                    store.save(
                        merged or fact["content"], scope=scope,
                        category=record.category, source="observed", approved=False,
                    )
                )
            elif decision == "DELETE" and record is not None:
                store.delete(record.id, scope=scope)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Consolidation save failed: %s", exc)
    if staged:
        logger.info("Consolidated %d durable fact(s) from one turn", len(staged))
    return staged


async def maybe_consolidate(
    user_text: str,
    assistant_reply: str,
    llm_factory: Any,
    store_factory: Any,
    scope: str = "default",
) -> None:
    """Best-effort entry point for the voice loop. Never raises."""
    try:
        settings = get_settings()
        if not getattr(settings, "JEV_MEMORY_CONSOLIDATE", True):
            return
        if len((user_text or "").strip()) < 20:
            return
        llm = llm_factory()
        store = store_factory()
        await consolidate_turn(user_text, assistant_reply, llm, store, scope)
    except Exception as exc:  # noqa: BLE001 — the turn already succeeded
        logger.debug("Background consolidation skipped: %s", exc)
