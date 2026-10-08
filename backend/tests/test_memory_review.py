"""Tests for the memory pending-review queue API (list/approve/reject)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uuid import UUID

import app.api.v1.memory as memory_api
from app.services.memory.store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    return MemoryStore(str(tmp_path / "review.db"))


@pytest.fixture()
def client(store, monkeypatch):
    monkeypatch.setattr(memory_api, "get_memory_store", lambda: store)
    app = FastAPI()
    app.include_router(memory_api.router, prefix="/memory")
    return TestClient(app)


def _seed_pending(store, n=3):
    ids = []
    for i in range(n):
        record = store.save(
            f"observed fact number {i} about routines",
            scope="default",
            category="routine",
            source="observed",
            approved=False,
        )
        ids.append(str(record.id))
    return ids


def test_pending_queue_lists_only_unapproved_oldest_first(client, store):
    store.save("explicit approved memory", approved=True)
    pending_ids = _seed_pending(store, 3)

    response = client.get("/memory/pending")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    returned_ids = [m["id"] for m in body["memories"]]
    assert returned_ids == pending_ids  # oldest first
    assert all(m["approved"] is False for m in body["memories"])
    assert all(m["source"] == "observed" for m in body["memories"])


def test_pending_queue_empty_by_default(client):
    response = client.get("/memory/pending")
    assert response.status_code == 200
    assert response.json() == {"memories": [], "count": 0}


def test_approve_pending_memory(client, store):
    (pending_id,) = _seed_pending(store, 1)

    response = client.post(f"/memory/pending/{pending_id}/approve")
    assert response.status_code == 200
    assert response.json()["approved"] is True

    # Now visible in the normal list, gone from the queue.
    assert client.get("/memory/pending").json()["count"] == 0
    listed = client.get("/memory/").json()
    assert any(m["id"] == pending_id and m["approved"] for m in listed["memories"])


def test_approve_missing_memory_returns_404(client):
    response = client.post(
        "/memory/pending/12345678-1234-5678-1234-567812345678/approve"
    )
    assert response.status_code == 404


def test_reject_pending_memory_deletes_it(client, store):
    (pending_id,) = _seed_pending(store, 1)

    response = client.post(f"/memory/pending/{pending_id}/reject")
    assert response.status_code == 200
    assert response.json()["rejected"] is True

    assert client.get("/memory/pending").json()["count"] == 0
    assert store.get(UUID(pending_id)) is None


def test_reject_missing_memory_returns_404(client):
    response = client.post(
        "/memory/pending/12345678-1234-5678-1234-567812345678/reject"
    )
    assert response.status_code == 404


def test_create_memory_with_phase2_fields(client):
    response = client.post(
        "/memory/",
        json={
            "content": "Aarya's gym membership renews each January",
            "category": "routine",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
            "trust": 0.8,
            "provenance": "user:explicit",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["valid_from"].replace("Z", "+00:00") == "2026-01-01T00:00:00+00:00"
    assert body["valid_to"].replace("Z", "+00:00") == "2027-01-01T00:00:00+00:00"
    assert body["trust"] == 0.8
    assert body["provenance"] == "user:explicit"


def test_create_memory_rejects_inverted_validity_window(client):
    response = client.post(
        "/memory/",
        json={
            "content": "bad window",
            "valid_from": "2027-01-01T00:00:00+00:00",
            "valid_to": "2026-01-01T00:00:00+00:00",
        },
    )
    assert response.status_code == 400


def test_set_validity_and_trust_endpoints(client, store):
    record = store.save("a durable preference")
    memory_id = str(record.id)

    response = client.patch(
        f"/memory/{memory_id}/validity",
        json={"valid_from": "2026-10-01T00:00:00+00:00", "valid_to": None},
    )
    assert response.status_code == 200
    assert response.json()["valid_from"].replace("Z", "+00:00") == "2026-10-01T00:00:00+00:00"
    assert response.json()["valid_to"] is None

    response = client.patch(
        f"/memory/{memory_id}/trust",
        json={"trust": 0.5, "provenance": "consolidation:observed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["trust"] == 0.5
    assert body["provenance"] == "consolidation:observed"


def test_set_validity_missing_memory_returns_404(client):
    response = client.patch(
        "/memory/12345678-1234-5678-1234-567812345678/validity",
        json={"valid_from": "2026-10-01T00:00:00+00:00"},
    )
    assert response.status_code == 404


def test_set_validity_rejects_bad_iso(client, store):
    memory_id = str(store.save("another fact").id)
    response = client.patch(
        f"/memory/{memory_id}/validity", json={"valid_from": "not-a-date"}
    )
    assert response.status_code == 400
