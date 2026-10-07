"""Tests for background memory consolidation (extract -> reconcile -> stage)."""

import json
from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.services.memory.consolidate import (
    consolidate_turn,
    extract_facts,
    maybe_consolidate,
    reconcile_fact,
)


@dataclass
class _FakeRecord:
    id: object
    content: str
    category: str = "general"


class _FakeLLM:
    """Yields canned strict-JSON replies."""

    def __init__(self, replies):
        self._replies = list(replies)

    async def generate(self, messages, temperature=0.1, max_tokens=600):
        yield self._replies.pop(0)


class _FakeStore:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.saved = []
        self.deleted = []

    def search(self, query, scope="default", limit=5):
        return self.existing

    def save(self, content, scope="default", category="general", source="explicit",
             approved=True):
        record = _FakeRecord(uuid4(), content, category)
        self.saved.append({"content": content, "source": source, "approved": approved})
        return record

    def delete(self, memory_id, scope="default"):
        self.deleted.append(memory_id)
        return True


def _llm_for_extract(facts):
    return _FakeLLM([json.dumps({"facts": facts})])


@pytest.mark.asyncio
async def test_extract_facts_parses_strict_json():
    llm = _llm_for_extract([
        {"content": "Aarya prefers morning workouts", "category": "preference"},
        {"content": "x", "category": "general"},  # too short -> dropped
    ])
    facts = await extract_facts("User: I prefer morning workouts", llm)
    assert facts == [
        {"content": "Aarya prefers morning workouts", "category": "preference"}
    ]


@pytest.mark.asyncio
async def test_extract_facts_empty_on_chitchat():
    llm = _llm_for_extract([])
    assert await extract_facts("User: hello", llm) == []


@pytest.mark.asyncio
async def test_reconcile_noop_on_duplicate():
    existing = [_FakeRecord(uuid4(), "Aarya prefers morning workouts")]
    decision, merged, record = await reconcile_fact(
        {"content": "Aarya prefers morning workouts!", "category": "preference"},
        existing, _FakeLLM([]),
    )
    assert decision == "NOOP" and record is existing[0]


@pytest.mark.asyncio
async def test_reconcile_add_when_novel():
    decision, _, _ = await reconcile_fact(
        {"content": "Aarya is learning German", "category": "goal"},
        [_FakeRecord(uuid4(), "Aarya prefers morning workouts")],
        _FakeLLM([]),
    )
    assert decision == "ADD"


@pytest.mark.asyncio
async def test_reconcile_llm_update():
    existing = [_FakeRecord(uuid4(), "Aarya wakes up at 6am")]
    llm = _FakeLLM([json.dumps({
        "decision": "UPDATE",
        "merged": "Aarya wakes up at 6:30am on weekdays",
    })])
    decision, merged, record = await reconcile_fact(
        {"content": "Aarya now wakes up at 6:30 on weekdays", "category": "routine"},
        existing, llm,
    )
    assert decision == "UPDATE"
    assert merged == "Aarya wakes up at 6:30am on weekdays"


@pytest.mark.asyncio
async def test_consolidate_turn_stages_pending_memories():
    store = _FakeStore()
    llm = _llm_for_extract([
        {"content": "Aarya prefers dark chocolate", "category": "preference"},
    ])
    staged = await consolidate_turn(
        "I really prefer dark chocolate over milk",
        "Noted — dark chocolate it is.",
        llm, store,
    )
    assert len(staged) == 1
    assert store.saved[0]["source"] == "observed"
    assert store.saved[0]["approved"] is False


@pytest.mark.asyncio
async def test_consolidate_turn_skips_duplicates():
    store = _FakeStore(existing=[
        _FakeRecord(uuid4(), "Aarya prefers dark chocolate"),
    ])
    llm = _llm_for_extract([
        {"content": "Aarya prefers dark chocolate", "category": "preference"},
    ])
    staged = await consolidate_turn("dark chocolate please", "Noted.", llm, store)
    assert staged == [] and store.saved == []


@pytest.mark.asyncio
async def test_maybe_consolidate_never_raises():
    async def boom_factory():
        raise RuntimeError("no llm here")

    # Short text -> skipped silently; broken factory -> swallowed.
    await maybe_consolidate("hi", "hello", boom_factory, lambda: None)
    await maybe_consolidate(
        "this is a longer user message for sure", "ok", boom_factory, lambda: None
    )
