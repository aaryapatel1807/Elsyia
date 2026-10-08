"""Tests for the MemOS-style phase-2 memory schema.

Covers: safe migration of legacy databases, temporal validity gating in
retrieval, trust-weighted ranking, and the set_validity / set_trust
store methods.
"""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.services.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    return MemoryStore(str(tmp_path / "phase2.db"))


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _iso_days_ahead(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def test_legacy_database_migrates_safely(tmp_path):
    """A pre-phase-2 database gains the new columns with sane defaults."""
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            embedding TEXT,
            embedding_version TEXT NOT NULL DEFAULT 'legacy',
            source TEXT NOT NULL DEFAULT 'explicit',
            approved INTEGER NOT NULL DEFAULT 1,
            encrypted INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    now = datetime.now(timezone.utc).isoformat()
    legacy_id = "12345678-1234-5678-1234-567812345678"
    connection.execute(
        "INSERT INTO memories(id, scope, content, category, created_at, updated_at) "
        "VALUES (?, 'default', 'old fact', 'general', ?, ?)",
        (legacy_id, now, now),
    )
    connection.commit()
    connection.close()

    store = MemoryStore(str(db_path))
    check = sqlite3.connect(db_path)
    check.row_factory = sqlite3.Row
    columns = {row["name"] for row in check.execute("PRAGMA table_info(memories)")}
    check.close()
    assert {"valid_from", "valid_to", "trust", "provenance"} <= columns

    # Old row reads back with phase-2 defaults: always valid, full trust.
    records = store.list("default")
    assert len(records) == 1
    record = records[0]
    assert record.valid_from is None
    assert record.valid_to is None
    assert record.trust == 1.0
    assert record.provenance == "explicit"
    # And it is still retrievable (old behaviour preserved).
    assert store.search("old fact") != []


def test_search_excludes_expired_memories(store):
    store.save("Aarya's flight is on Friday", valid_to=_iso_days_ago(2))
    store.save("Aarya prefers morning workouts")

    results = store.search("Aarya flight Friday")
    assert all("flight" not in r.content for r in results)


def test_search_excludes_not_yet_valid_memories(store):
    store.save("Aarya starts the new job next quarter", valid_from=_iso_days_ahead(30))
    store.save("Aarya prefers morning workouts")

    results = store.search("Aarya new job quarter")
    assert all("new job" not in r.content for r in results)


def test_search_includes_currently_valid_memories(store):
    store.save(
        "Aarya's gym membership is active",
        valid_from=_iso_days_ago(10),
        valid_to=_iso_days_ahead(300),
    )
    results = store.search("gym membership active")
    assert any("gym membership" in r.content for r in results)


def test_trust_weights_ranking(store):
    # Same content, different trust: the trusted one must rank first.
    store.save("the blue widget is in the garage", trust=0.1)
    store.save("the blue widget is in the garage", trust=1.0)

    results = store.search("blue widget garage")
    assert len(results) == 2
    assert results[0].trust == 1.0
    assert results[1].trust == 0.1


def test_zero_trust_memory_still_retrievable_when_very_relevant(store):
    record = store.save("the red bicycle is fast", trust=0.0)
    results = store.search("red bicycle fast")
    assert any(r.id == record.id for r in results)


def test_set_validity_round_trip(store):
    record = store.save("a time-bound fact")
    assert store.set_validity(
        record.id,
        valid_from="2026-10-01T00:00:00+00:00",
        valid_to="2026-12-31T00:00:00+00:00",
    )
    fetched = store.get(record.id)
    assert fetched is not None
    assert fetched.valid_from == "2026-10-01T00:00:00+00:00"
    assert fetched.valid_to == "2026-12-31T00:00:00+00:00"

    # Clearing with None works.
    assert store.set_validity(record.id, valid_from=None, valid_to=None)
    fetched = store.get(record.id)
    assert fetched is not None
    assert fetched.valid_from is None
    assert fetched.valid_to is None


def test_set_validity_rejects_inverted_window(store):
    record = store.save("another fact")
    with pytest.raises(ValueError):
        store.set_validity(
            record.id,
            valid_from="2027-01-01T00:00:00+00:00",
            valid_to="2026-01-01T00:00:00+00:00",
        )


def test_set_validity_rejects_bad_iso(store):
    record = store.save("yet another fact")
    with pytest.raises(ValueError):
        store.set_validity(record.id, valid_from="tomorrow-ish")


def test_set_trust_round_trip_and_clamping(store):
    record = store.save("a shaky rumour", provenance="import:notes")
    assert store.set_trust(record.id, trust=0.25, provenance="user:corrected")
    fetched = store.get(record.id)
    assert fetched is not None
    assert fetched.trust == 0.25
    assert fetched.provenance == "user:corrected"

    # Out-of-range values clamp instead of exploding voice turns.
    assert store.set_trust(record.id, trust=7.5)
    assert store.get(record.id).trust == 1.0
    assert store.set_trust(record.id, trust=-2.0)
    assert store.get(record.id).trust == 0.0


def test_set_validity_missing_id_returns_false(store):
    from uuid import uuid4

    assert store.set_validity(uuid4(), valid_from="2026-10-01T00:00:00+00:00") is False
    assert store.set_trust(uuid4(), trust=0.5) is False
    assert store.get(uuid4()) is None


def test_save_validates_window_and_provenance_defaults_to_source(store):
    record = store.save("windowed", source="observed")
    assert record.provenance == "observed"
    assert record.trust == 1.0
    with pytest.raises(ValueError):
        store.save(
            "bad",
            valid_from="2027-01-01T00:00:00+00:00",
            valid_to="2026-01-01T00:00:00+00:00",
        )
