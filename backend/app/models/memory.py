"""Pydantic models for persistent memory APIs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreateRequest(BaseModel):
    """Request to save one user-approved memory."""

    content: str = Field(..., min_length=1, max_length=10000)
    scope: str = Field(default="default", min_length=1, max_length=100)
    category: str = Field(default="general", min_length=1, max_length=50)
    valid_from: str | None = Field(default=None, description="ISO-8601 start of validity")
    valid_to: str | None = Field(default=None, description="ISO-8601 end of validity")
    trust: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: str | None = Field(default=None, max_length=50)


class MemoryResponse(BaseModel):
    """Persisted memory returned by the API."""

    id: UUID
    scope: str
    content: str
    category: str
    created_at: datetime
    updated_at: datetime
    source: str = "explicit"
    approved: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    trust: float = 1.0
    provenance: str = "explicit"


class MemoryPendingResponse(BaseModel):
    """The pending-review queue: staged facts awaiting approval."""

    memories: list[MemoryResponse]
    count: int


class MemoryValidityRequest(BaseModel):
    """Set (or clear with null) the temporal validity window of a memory."""

    valid_from: str | None = Field(default=None, description="ISO-8601 start of validity")
    valid_to: str | None = Field(default=None, description="ISO-8601 end of validity")


class MemoryTrustRequest(BaseModel):
    """Set the trust score and provenance of a memory."""

    trust: float = Field(..., ge=0.0, le=1.0)
    provenance: str | None = Field(default=None, max_length=50)


class MemoryListResponse(BaseModel):
    """Collection of persisted memories."""

    memories: list[MemoryResponse]
    count: int


class MemoryClearResponse(BaseModel):
    """Result of clearing a memory scope."""

    deleted: int
    scope: str


class MemoryStatsResponse(BaseModel):
    """Privacy-safe memory index statistics."""

    scope: str
    total: int
    pending: int = 0
    indexed: int
    encrypted: bool


class MemoryReindexResponse(BaseModel):
    """Result of rebuilding memory vectors."""

    scope: str | None
    reindexed: int
    embedding_version: str


class MemoryExportResponse(BaseModel):
    """Decrypted user-visible memory export."""

    scope: str
    memories: list[dict[str, Any]]
    count: int
