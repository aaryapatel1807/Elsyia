"""Tests for conversation compaction and memory-store embedding persistence."""

from uuid import uuid4

import pytest

from app.models import Message, MessageRole
from app.services.chat.conversation import ConversationManager
from app.services.memory.store import MemoryStore


def _manager_with_messages(n):
    manager = ConversationManager()
    cid = uuid4()
    for i in range(n):
        manager.add_message(cid, MessageRole.USER, f"question {i}")
        manager.add_message(cid, MessageRole.ASSISTANT, f"answer {i}")
    return manager, cid


def test_compact_drops_oldest_and_keeps_summary():
    manager, cid = _manager_with_messages(10)  # 20 messages
    dropped = manager.compact(cid, "User asked about Python.", keep_last_n=6)
    assert dropped == 14
    conv = manager.get_history(cid)
    assert len(conv.messages) == 6
    assert conv.messages[0].content == "question 7"
    assert "Python" in conv.summary


def test_compact_appends_to_existing_summary():
    manager, cid = _manager_with_messages(10)
    manager.compact(cid, "First part.", keep_last_n=6)
    manager.compact(cid, "Second part.", keep_last_n=4)
    conv = manager.get_history(cid)
    assert "First part." in conv.summary and "Second part." in conv.summary
    assert len(conv.messages) == 4


def test_compact_noop_when_short():
    manager, cid = _manager_with_messages(2)
    assert manager.compact(cid, "summary", keep_last_n=6) == 0
    assert manager.get_history(cid).summary == ""


def test_conversation_history_defaults_summary_empty():
    manager = ConversationManager()
    conv = manager.get_or_create()
    assert conv.summary == ""


def test_search_persists_refreshed_embeddings(tmp_path):
    db = tmp_path / "mem.db"
    store = MemoryStore(str(db))
    store.save("Aarya likes strong coffee", scope="test-scope")
    # Corrupt the stored embedding so search must recompute it.
    import sqlite3

    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE memories SET embedding = NULL, embedding_version = 'old'")
        conn.commit()
    store.search("coffee", scope="test-scope")
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT embedding, embedding_version FROM memories"
        ).fetchone()
    assert row[0]  # embedding was written back
    assert row[1] != "old"
