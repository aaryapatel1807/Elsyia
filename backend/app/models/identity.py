"""Provider-neutral identity and session schemas for Phase 12."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IdentityAuthStatusResponse(BaseModel):
    admin_token_configured: bool
    session_signing_key_configured: bool
    sso_enabled: bool
    sso_configured: bool
    mfa_readiness_enabled: bool


class SessionCreateRequest(BaseModel):
    admin_token: str


class SessionResponse(BaseModel):
    session_token: str
    session_id: str
    principal_id: str
    role: str
    expires_at: datetime


class SessionMeResponse(BaseModel):
    session_id: str
    principal_id: str
    role: str
    created_at: datetime
    expires_at: datetime


class SsoStartResponse(BaseModel):
    enabled: bool
    configured: bool
    message: str


class MfaEnrollmentResponse(BaseModel):
    enrollment_id: str
    principal_id: str
    provider: str
    status: str
