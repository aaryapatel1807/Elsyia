"""API schemas for local-first Phase 11 synchronization."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SyncStatusResponse(BaseModel):
    enabled: bool
    cloud_enabled: bool
    cloud_configured: bool
    device_id: str
    backup_count: int
    latest_sequence: int | None


class BackupResponse(BaseModel):
    id: str
    filename: str
    size_bytes: int
    digest_prefix: str
    sequence: int
    device_id: str
    created_at: str
    status: str


class BackupListResponse(BaseModel):
    backups: list[BackupResponse]


class RestorePreviewFile(BaseModel):
    key: str
    state: str
    size_bytes: int


class RestorePreviewResponse(BaseModel):
    backup_id: str
    device_id: str
    sequence: int
    created_at: str
    files: list[RestorePreviewFile]
    conflicts: list[str]
    requires_confirmation: bool


class RestoreRequest(BaseModel):
    backup_id: str = Field(min_length=1, max_length=200)
    confirm: bool = False
    force: bool = False
    decisions: dict[str, str] | None = None


class ConflictResolutionRequest(BaseModel):
    backup_id: str = Field(min_length=1, max_length=200)
    decisions: dict[str, str] = Field(min_length=1, max_length=20)


class RestoreResponse(BaseModel):
    backup_id: str
    restored: int
    safety_backup: str


class CloudSyncResponse(BaseModel):
    enabled: bool
    message: str
