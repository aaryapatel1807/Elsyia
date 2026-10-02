"""REST API for the Phase 11 local-first synchronization foundation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core import get_settings
from app.models.sync import (
    BackupListResponse,
    BackupResponse,
    CloudSyncResponse,
    ConflictResolutionRequest,
    RestorePreviewFile,
    RestorePreviewResponse,
    RestoreRequest,
    RestoreResponse,
    SyncStatusResponse,
)
from app.services.enterprise import get_enterprise_manager
from app.services.sync import SyncAuthError, SyncError, SyncTransport, get_sync_manager

router = APIRouter()


def _backup_response(record) -> BackupResponse:
    return BackupResponse(
        id=record.id,
        filename=record.filename,
        size_bytes=record.size_bytes,
        digest_prefix=record.digest_prefix,
        sequence=record.sequence,
        device_id=record.device_id,
        created_at=record.created_at,
        status=record.status,
    )


def _sync_error(exc: SyncError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/status", response_model=SyncStatusResponse)
def sync_status() -> SyncStatusResponse:
    settings = get_settings()
    manager = get_sync_manager()
    backups = manager.list_backups()
    return SyncStatusResponse(
        enabled=settings.SYNC_ENABLED,
        cloud_enabled=settings.SYNC_CLOUD_ENABLED,
        cloud_configured=bool(settings.SYNC_CLOUD_ENDPOINT.strip()),
        device_id=manager._device_id(),
        backup_count=len(backups),
        latest_sequence=backups[0].sequence if backups else None,
    )


@router.post("/backup", response_model=BackupResponse, status_code=status.HTTP_201_CREATED)
def create_backup() -> BackupResponse:
    try:
        return _backup_response(get_sync_manager().create_backup())
    except SyncError as exc:
        raise _sync_error(exc) from exc


@router.get("/backups", response_model=BackupListResponse)
def list_backups() -> BackupListResponse:
    return BackupListResponse(
        backups=[_backup_response(item) for item in get_sync_manager().list_backups()]
    )


@router.post("/restore/preview", response_model=RestorePreviewResponse)
def preview_restore(request: RestoreRequest) -> RestorePreviewResponse:
    try:
        preview = get_sync_manager().preview_restore(request.backup_id)
    except SyncError as exc:
        raise _sync_error(exc) from exc
    return RestorePreviewResponse(
        backup_id=preview["backup_id"],
        device_id=preview["device_id"],
        sequence=preview["sequence"],
        created_at=preview["created_at"],
        files=[RestorePreviewFile(**item) for item in preview["files"]],
        conflicts=preview["conflicts"],
        requires_confirmation=preview["requires_confirmation"],
    )


@router.post("/restore", response_model=RestoreResponse)
def restore(request: RestoreRequest) -> RestoreResponse:
    try:
        result = get_sync_manager().restore(
            request.backup_id,
            confirm=request.confirm,
            force=request.force,
            decisions=request.decisions,
        )
    except SyncError as exc:
        raise _sync_error(exc) from exc
    return RestoreResponse(**result)


@router.post("/resolve")
def resolve_conflicts(request: ConflictResolutionRequest) -> dict[str, object]:
    try:
        return get_sync_manager().resolve_conflicts(request.backup_id, request.decisions)
    except SyncError as exc:
        raise _sync_error(exc) from exc


@router.post("/push", response_model=CloudSyncResponse)
def push() -> CloudSyncResponse:
    settings = get_settings()
    if not settings.SYNC_CLOUD_ENABLED:
        return CloudSyncResponse(
            enabled=False,
            message="Cloud sync is disabled. No remote request was made.",
        )
    if settings.ENTERPRISE_ENABLED and not get_enterprise_manager().policy_enabled("allow_cloud_sync"):
        raise HTTPException(status_code=403, detail="Enterprise policy blocks cloud synchronization")
    try:
        result = SyncTransport(get_sync_manager()).push_latest()
    except (SyncAuthError, SyncError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CloudSyncResponse(
        enabled=True,
        message=f"Encrypted package transmitted successfully; relay status {result.status_code}. Remote ID: {result.remote_id or 'not returned'}.",
    )


@router.get("/pull", response_model=CloudSyncResponse)
def pull() -> CloudSyncResponse:
    settings = get_settings()
    if not settings.SYNC_CLOUD_ENABLED:
        return CloudSyncResponse(
            enabled=False,
            message="Cloud sync is disabled. No remote request was made.",
        )
    if settings.ENTERPRISE_ENABLED and not get_enterprise_manager().policy_enabled("allow_cloud_sync"):
        raise HTTPException(status_code=403, detail="Enterprise policy blocks cloud synchronization")
    try:
        package = SyncTransport(get_sync_manager()).pull()
        record = get_sync_manager().import_package(package)
    except (SyncAuthError, SyncError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CloudSyncResponse(
        enabled=True,
        message=f"Encrypted package received and stored locally as backup sequence {record.sequence}.",
    )
