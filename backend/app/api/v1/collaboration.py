"""Local workspace invitation API for Phase 12 collaboration readiness."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, status

from app.models.collaboration import (
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationCreateRequest,
    InvitationResponse,
)
from app.services.enterprise import EnterpriseError, get_enterprise_manager

router = APIRouter()


def _session(authorization: str | None) -> str:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Bearer admin session is required")
    return authorization[len(prefix) :].strip()


def _require_session(authorization: str | None) -> str:
    token = _session(authorization)
    try:
        get_enterprise_manager().require_session(token)
    except EnterpriseError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return token


def _invitation(value: dict, include_token: bool = False) -> InvitationResponse:
    return InvitationResponse(
        id=value["id"],
        display_name=value["display_name"],
        role=value["role"],
        status=value["status"],
        created_at=datetime.fromisoformat(value["created_at"]),
        expires_at=datetime.fromisoformat(value["expires_at"]),
        accepted_member_id=value.get("accepted_member_id"),
        invitation_token=value.get("invitation_token") if include_token else None,
    )


@router.post("/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(request: InvitationCreateRequest, authorization: str | None = Header(default=None)) -> InvitationResponse:
    token = _require_session(authorization)
    try:
        return _invitation(get_enterprise_manager().create_invitation(token, request.display_name, request.role, request.ttl_hours), include_token=True)
    except EnterpriseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/invitations", response_model=list[InvitationResponse])
def list_invitations(authorization: str | None = Header(default=None)) -> list[InvitationResponse]:
    _require_session(authorization)
    return [_invitation(item) for item in get_enterprise_manager().list_invitations()]


@router.post("/invitations/{invitation_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: str, authorization: str | None = Header(default=None)) -> None:
    _require_session(authorization)
    try:
        get_enterprise_manager().revoke_invitation(invitation_id)
    except EnterpriseError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.post("/invitations/accept", response_model=InvitationAcceptResponse)
def accept_invitation(request: InvitationAcceptRequest) -> InvitationAcceptResponse:
    try:
        member = get_enterprise_manager().accept_invitation(request.invitation_token)
    except EnterpriseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InvitationAcceptResponse(
        member_id=member.id,
        display_name=member.display_name,
        role=member.role,
        status=member.status,
        message="Invitation accepted as a pending member; identity-provider login is required before activation.",
    )
