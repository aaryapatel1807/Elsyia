"""Local workspace collaboration and invitation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InvitationCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "member", "viewer"] = "member"
    ttl_hours: int = Field(default=72, ge=1, le=168)


class InvitationResponse(BaseModel):
    id: str
    display_name: str
    role: str
    status: str
    created_at: datetime
    expires_at: datetime
    accepted_member_id: str | None = None
    invitation_token: str | None = None


class InvitationAcceptRequest(BaseModel):
    invitation_token: str = Field(min_length=1, max_length=256)


class InvitationAcceptResponse(BaseModel):
    member_id: str
    display_name: str
    role: str
    status: str
    message: str
