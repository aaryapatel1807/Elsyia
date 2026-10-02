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
    MemoryReindexResponse,
    MemoryResponse,
    MemoryStatsResponse,
)
from app.services.memory import MemoryRecord, get_memory_store

logger = get_logger("api.memory")
router = APIRouter()


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
            get_memory_store().save(request.content, request.scope, request.category)
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
