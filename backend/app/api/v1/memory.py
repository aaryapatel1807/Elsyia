"""Persistent memory management endpoints."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.core import get_logger, get_settings
from app.models import (
    MemoryClearResponse,
    MemoryCreateRequest,
    MemoryExportResponse,
    MemoryListResponse,
    MemoryPendingResponse,
    MemoryReindexResponse,
    MemoryResponse,
    MemoryStatsResponse,
    MemoryTrustRequest,
    MemoryValidityRequest,
)
from app.services.memory import MemoryRecord, get_memory_store

logger = get_logger("api.memory")
router = APIRouter()


def _to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_response(record: MemoryRecord) -> MemoryResponse:
    """Convert a storage record to the public API model."""
    return MemoryResponse(
        id=record.id,
        scope=record.scope,
        content=record.content,
        category=record.category,
        created_at=datetime.fromisoformat(record.created_at),
        updated_at=datetime.fromisoformat(record.updated_at),
        source=record.source,
        approved=record.approved,
        valid_from=_to_datetime(record.valid_from),
        valid_to=_to_datetime(record.valid_to),
        trust=record.trust,
        provenance=record.provenance,
    )


def _ensure_enabled() -> None:
    if not get_settings().ENABLE_MEMORY:
        raise HTTPException(status_code=503, detail="Memory is disabled")


@router.post("/", response_model=MemoryResponse, status_code=201)
def create_memory(request: MemoryCreateRequest) -> MemoryResponse:
    """Save one memory only when the user explicitly requests it."""
    _ensure_enabled()
    try:
        return _to_response(
            get_memory_store().save(
                request.content,
                request.scope,
                request.category,
                valid_from=request.valid_from,
                valid_to=request.valid_to,
                trust=request.trust,
                provenance=request.provenance,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/", response_model=MemoryListResponse)
def list_memories(
    scope: str = Query(default="default", min_length=1, max_length=100),
    query: str | None = Query(default=None, max_length=1000),
    include_pending: bool = Query(default=False),
) -> MemoryListResponse:
    """List memories or retrieve relevant memories for a query."""
    _ensure_enabled()
    store = get_memory_store()
    try:
        records = (
            store.search(query, scope)
            if query
            else store.list(scope, include_pending=include_pending)
        )
    except Exception as exc:
        logger.error("Memory retrieval failed: %s", exc)
        raise HTTPException(status_code=500, detail="Memory retrieval failed") from exc
    memories = [_to_response(record) for record in records]
    return MemoryListResponse(memories=memories, count=len(memories))


@router.get("/stats", response_model=MemoryStatsResponse)
def memory_stats(
    scope: str = Query(default="default", min_length=1, max_length=100),
) -> MemoryStatsResponse:
    """Return index statistics without returning memory content."""
    _ensure_enabled()
    return MemoryStatsResponse(**get_memory_store().stats(scope))


@router.post("/reindex", response_model=MemoryReindexResponse)
def reindex_memories(
    scope: str | None = Query(default=None, max_length=100),
) -> MemoryReindexResponse:
    """Rebuild neural vectors after an embedding model or version change."""
    _ensure_enabled()
    count = get_memory_store().reindex(scope)
    return MemoryReindexResponse(
        scope=scope,
        reindexed=count,
        embedding_version=get_settings().MEMORY_EMBEDDING_VERSION,
    )


@router.get("/export", response_model=MemoryExportResponse)
def export_memories(
    scope: str = Query(default="default", min_length=1, max_length=100),
) -> MemoryExportResponse:
    """Export decrypted user-visible memories for backup or review."""
    _ensure_enabled()
    memories = get_memory_store().export(scope)
    return MemoryExportResponse(scope=scope, memories=memories, count=len(memories))


@router.get("/pending", response_model=MemoryPendingResponse)
def list_pending_memories(
    scope: str = Query(default="default", min_length=1, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> MemoryPendingResponse:
    """List the pending-review queue: staged facts awaiting approval.

    The background consolidation pipeline writes observed facts here with
    approved=False; nothing in this queue is used for retrieval until
    approved. Ordered oldest-first so review follows arrival order.
    """
    _ensure_enabled()
    records = get_memory_store().pending(scope, limit)
    memories = [_to_response(record) for record in records]
    return MemoryPendingResponse(memories=memories, count=len(memories))


@router.post("/pending/{memory_id}/approve")
def approve_pending_memory(
    memory_id: UUID, scope: str = Query(default="default")
) -> dict[str, object]:
    """Approve one pending memory from the review queue for future retrieval."""
    _ensure_enabled()
    approved = get_memory_store().approve(memory_id, scope)
    if not approved:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"approved": True, "id": memory_id, "scope": scope}


@router.post("/pending/{memory_id}/reject")
def reject_pending_memory(
    memory_id: UUID, scope: str = Query(default="default")
) -> dict[str, object]:
    """Reject one pending memory from the review queue (deletes it)."""
    _ensure_enabled()
    deleted = get_memory_store().delete(memory_id, scope)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"rejected": True, "id": memory_id, "scope": scope}


@router.patch("/{memory_id}/validity", response_model=MemoryResponse)
def set_memory_validity(
    memory_id: UUID,
    request: MemoryValidityRequest,
    scope: str = Query(default="default"),
) -> MemoryResponse:
    """Set (or clear with null) the temporal validity window of a memory."""
    _ensure_enabled()
    store = get_memory_store()
    try:
        updated = store.set_validity(
            memory_id,
            scope,
            valid_from=request.valid_from,
            valid_to=request.valid_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")
    record = store.get(memory_id, scope)
    assert record is not None
    return _to_response(record)


@router.patch("/{memory_id}/trust", response_model=MemoryResponse)
def set_memory_trust(
    memory_id: UUID,
    request: MemoryTrustRequest,
    scope: str = Query(default="default"),
) -> MemoryResponse:
    """Set the trust score (0..1) and provenance of a memory."""
    _ensure_enabled()
    store = get_memory_store()
    try:
        updated = store.set_trust(
            memory_id, scope, trust=request.trust, provenance=request.provenance
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")
    record = store.get(memory_id, scope)
    assert record is not None
    return _to_response(record)


@router.post("/{memory_id}/approve")
def approve_memory(memory_id: UUID, scope: str = Query(default="default")) -> dict[str, object]:
    """Approve one background-extracted memory for future retrieval."""
    _ensure_enabled()
    approved = get_memory_store().approve(memory_id, scope)
    if not approved:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"approved": True, "id": memory_id, "scope": scope}


@router.delete("/{memory_id}")
def delete_memory(memory_id: UUID, scope: str = Query(default="default")) -> dict[str, object]:
    """Delete one memory in the requested scope."""
    _ensure_enabled()
    deleted = get_memory_store().delete(memory_id, scope)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True, "id": memory_id, "scope": scope}


@router.delete("/", response_model=MemoryClearResponse)
def clear_memories(scope: str = Query(default="default")) -> MemoryClearResponse:
    """Delete every memory in the requested scope."""
    _ensure_enabled()
    return MemoryClearResponse(deleted=get_memory_store().clear(scope), scope=scope)
