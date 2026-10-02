"""REST API for local-first normalized input attachments."""

from __future__ import annotations

import base64
import binascii
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core import get_settings
from app.models.input import (
    AttachmentListResponse,
    AttachmentResponse,
    CameraInputRequest,
    ClipboardInputRequest,
    CleanupResponse,
    FileIngestRequest,
    HandwritingInputRequest,
    InputStatusResponse,
    ProcessAttachmentRequest,
    ProcessingJobResponse,
)
from app.services.input import InputValidationError, get_attachment_store
from app.services.tools.base import ToolError
from app.services.tools.vision_tools import OcrImageTool

router = APIRouter()


def _job_response(job) -> ProcessingJobResponse | None:
    if job is None:
        return None
    return ProcessingJobResponse(
        id=job.id,
        attachment_token=job.attachment_token,
        status=job.status,
        summary=job.summary,
        error=job.error,
        extracted_chars=job.extracted_chars,
        truncated=job.truncated,
        provider=job.provider,
        memory_proposal_ids=list(job.memory_proposal_ids),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _response(event) -> AttachmentResponse:
    return AttachmentResponse(
        token=event.attachment_token,
        event_id=event.id,
        source=event.source,
        kind=event.kind,
        conversation_id=event.conversation_id,
        display_name=event.display_name,
        extension=event.extension,
        size_bytes=event.size_bytes,
        mime_type=event.mime_type,
        digest_prefix=event.digest_prefix,
        privacy=event.privacy,
        retention=event.retention,
        created_at=event.created_at,
        expires_at=event.expires_at,
        status=event.status,
        processing_job=_job_response(event.processing_job),
    )


@router.get("/status", response_model=InputStatusResponse)
def input_status() -> InputStatusResponse:
    settings = get_settings()
    store = get_attachment_store()
    return InputStatusResponse(
        enabled=settings.INPUT_ENABLED,
        attachment_count=len(store.list_attachments()),
    )


@router.post("/clipboard", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
def ingest_clipboard(request: ClipboardInputRequest) -> AttachmentResponse:
    try:
        event = get_attachment_store().ingest_bytes(
            request.content.encode("utf-8"),
            display_name="clipboard.txt",
            source="clipboard",
            conversation_id=request.conversation_id,
            kind="text",
            mime_type="text/plain; charset=utf-8",
        )
    except InputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _response(event)


@router.post("/camera", response_model=AttachmentResponse, status_code=status.HTTP_201_CREATED)
def ingest_camera(request: CameraInputRequest) -> AttachmentResponse:
    extension = Path(request.filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise HTTPException(status_code=400, detail="Camera input requires an allowed image filename extension")
    try:
        content = base64.b64decode(request.image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Camera payload is not valid base64") from exc
    try:
        event = get_attachment_store().ingest_bytes(
            content,
            display_name=request.filename,
            source="camera",
            conversation_id=request.conversation_id,
            kind="image",
            mime_type=mimetypes.guess_type(request.filename)[0] or "image/*",
        )
    except InputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _response(event)


@router.post("/handwriting")
async def recognize_handwriting(request: HandwritingInputRequest) -> dict[str, object]:
    try:
        path = get_attachment_store().get_attachment_path(request.attachment_token)
        result = await OcrImageTool().run(str(path))
    except (InputValidationError, ToolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "recognized", "attachment_token": request.attachment_token, **result}


@router.post("/ingest", response_model=list[AttachmentResponse], status_code=status.HTTP_201_CREATED)
def ingest_files(request: FileIngestRequest) -> list[AttachmentResponse]:
    try:
        events = get_attachment_store().ingest_files(
            request.paths,
            conversation_id=request.conversation_id,
        )
    except InputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_response(event) for event in events]


@router.post("/attachments/{token}/process", response_model=ProcessingJobResponse, status_code=202)
def process_attachment(token: str, request: ProcessAttachmentRequest) -> ProcessingJobResponse:
    try:
        job = get_attachment_store().enqueue_processing(token, force=request.force)
    except InputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = _job_response(job)
    assert result is not None
    return result


@router.get("/processing/{job_id}", response_model=ProcessingJobResponse)
def get_processing_job(job_id: str) -> ProcessingJobResponse:
    job = get_attachment_store().get_processing_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Processing job not found")
    result = _job_response(job)
    assert result is not None
    return result


@router.get("/attachments", response_model=AttachmentListResponse)
def list_attachments() -> AttachmentListResponse:
    return AttachmentListResponse(
        attachments=[_response(event) for event in get_attachment_store().list_attachments()]
    )


@router.delete("/attachments/{token}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(token: str) -> None:
    if not get_attachment_store().delete_attachment(token):
        raise HTTPException(status_code=404, detail="Attachment not found")


@router.post("/cleanup", response_model=CleanupResponse)
def cleanup_attachments() -> CleanupResponse:
    return CleanupResponse(expired_count=get_attachment_store().clear_expired())
