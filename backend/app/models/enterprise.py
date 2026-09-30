"""Pydantic schemas for the Phase 12 local enterprise foundation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class WorkspaceUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberResponse(BaseModel):
    id: str
    display_name: str
    role: Literal["owner", "admin", "member", "viewer"]
    status: Literal["active", "disabled"]
    created_at: datetime
    updated_at: datetime


class MemberCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "member", "viewer"] = "member"


class MemberUpdateRequest(BaseModel):
    role: Literal["owner", "admin", "member", "viewer"] | None = None
    status: Literal["active", "disabled"] | None = None


class PolicyResponse(BaseModel):
    key: str
    enabled: bool
    updated_at: datetime


class PolicyUpdateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    enabled: bool


class EnterpriseStatusResponse(BaseModel):
    enabled: bool
    workspace: WorkspaceResponse
    member_count: int
    analytics_opt_in: bool
    admin_auth_configured: bool


class PolicyListResponse(BaseModel):
    policies: list[PolicyResponse]


class MemberListResponse(BaseModel):
    members: list[MemberResponse]


class AuditEventCount(BaseModel):
    action: str
    status: str
    count: int


class AuditRecentEvent(BaseModel):
    action: str
    status: str
    created_at: datetime


class AuditSummaryResponse(BaseModel):
    events: list[AuditEventCount]
    recent: list[AuditRecentEvent]
    retention_days: int


class AnalyticsEvent(BaseModel):
    event: str
    count: int
    first_at: datetime
    last_at: datetime


class AnalyticsResponse(BaseModel):
    enabled: bool
    events: list[AnalyticsEvent]


class SharedAgentGrantRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    member_id: str = Field(min_length=1, max_length=128)
    capabilities: list[Literal["view", "prepare_run"]] = Field(min_length=1, max_length=2)


class SharedAgentRevokeRequest(BaseModel):
    grant_id: str = Field(min_length=1, max_length=128)
