"""Provider-neutral identity/session readiness API for Phase 12."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, status

from app.models.identity import (
    IdentityAuthStatusResponse,
    MfaEnrollmentResponse,
    SessionCreateRequest,
    SessionMeResponse,
    SessionResponse,
    SsoStartResponse,
)
from app.services.enterprise import EnterpriseError, get_enterprise_manager

router = APIRouter()


def _bearer(authorization: str | None) -> str:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Bearer session is required")
    return authorization[len(prefix) :].strip()


def _error(exc: EnterpriseError) -> HTTPException:
    message = str(exc)
    if "configured" in message or "disabled" in message:
        return HTTPException(status_code=503, detail=message)
    return HTTPException(status_code=401, detail=message)


@router.get("/status", response_model=IdentityAuthStatusResponse)
def auth_status() -> IdentityAuthStatusResponse:
    return IdentityAuthStatusResponse(**get_enterprise_manager().auth_status())


@router.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(request: SessionCreateRequest) -> SessionResponse:
    try:
        value = get_enterprise_manager().create_session(request.admin_token)
    except EnterpriseError as exc:
        raise _error(exc) from exc
    return SessionResponse(
        session_token=value["session_token"],
        session_id=value["session_id"],
        principal_id=value["principal_id"],
        role=value["role"],
        expires_at=datetime.fromisoformat(value["expires_at"]),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authorization: str | None = Header(default=None)) -> None:
    token = _bearer(authorization)
    try:
        get_enterprise_manager().revoke_session(token)
    except EnterpriseError as exc:
        raise _error(exc) from exc


@router.get("/me", response_model=SessionMeResponse)
def me(authorization: str | None = Header(default=None)) -> SessionMeResponse:
    token = _bearer(authorization)
    try:
        value = get_enterprise_manager().require_session(token)
    except EnterpriseError as exc:
        raise _error(exc) from exc
    return SessionMeResponse(
        session_id=value["session_id"],
        principal_id=value["principal_id"],
        role=value["role"],
        created_at=datetime.fromisoformat(value["created_at"]),
        expires_at=datetime.fromisoformat(value["expires_at"]),
    )


@router.post("/sso/start", response_model=SsoStartResponse)
def sso_start() -> SsoStartResponse:
    value = get_enterprise_manager().auth_status()
    if not value["sso_enabled"]:
        return SsoStartResponse(enabled=False, configured=False, message="External SSO is disabled; no identity-provider request was made.")
    if not value["sso_configured"]:
        return SsoStartResponse(enabled=True, configured=False, message="External SSO is enabled but not configured; no authorization URL was generated.")
    return SsoStartResponse(enabled=True, configured=True, message="The provider-neutral SSO adapter is not implemented; no authorization URL was generated.")


@router.post("/mfa/enroll", response_model=MfaEnrollmentResponse, status_code=status.HTTP_201_CREATED)
def enroll_mfa(authorization: str | None = Header(default=None)) -> MfaEnrollmentResponse:
    token = _bearer(authorization)
    try:
        value = get_enterprise_manager().enroll_mfa(token)
    except EnterpriseError as exc:
        raise _error(exc) from exc
    return MfaEnrollmentResponse(**value)
