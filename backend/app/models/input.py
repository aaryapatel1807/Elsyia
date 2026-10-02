"""Pydantic schemas for normalized local input attachments."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileIngestRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=50)
    conversation_id: str | None = Field(default=None, max_length=128)


class ClipboardInputRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = Field(default=None, max_length=128)


class CameraInputRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=20_000_000)
    filename: str = Field(default="camera.png", min_length=1, max_length=120)
    conversation_id: str | None = Field(default=None, max_length=128)


class HandwritingInputRequest(BaseModel):
    attachment_token: str = Field(min_length=8, max_length=100)


class ProcessingJobResponse(BaseModel):
    id: str
    attachment_token: str
    status: str
    summary: str | None
    error: str | None
    extracted_chars: int
    truncated: bool
    provider: str | None
    memory_proposal_ids: list[str]
    created_at: str
    updated_at: str


class AttachmentResponse(BaseModel):
    token: str
    event_id: str
    source: str
    kind: str
    conversation_id: str | None
    display_name: str
    extension: str
    size_bytes: int
    mime_type: str
    digest_prefix: str
    privacy: str
    retention: str
    created_at: str
    expires_at: str
    status: str
    processing_job: ProcessingJobResponse | None = None


class AttachmentListResponse(BaseModel):
    attachments: list[AttachmentResponse]


class ProcessAttachmentRequest(BaseModel):
    force: bool = False


class CleanupResponse(BaseModel):
    expired_count: int


class InputStatusResponse(BaseModel):
    enabled: bool
    attachment_count: int
