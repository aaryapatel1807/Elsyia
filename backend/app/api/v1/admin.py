"""Local enterprise administration API for Phase 12."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, status

from app.models.enterprise import (
    AnalyticsEvent,
    AnalyticsResponse,
    AuditEventCount,
    AuditRecentEvent,
    AuditSummaryResponse,
    EnterpriseStatusResponse,
    MemberCreateRequest,
    MemberListResponse,
    MemberResponse,
    MemberUpdateRequest,
    PolicyListResponse,
    PolicyResponse,
    PolicyUpdateRequest,
    WorkspaceResponse,
    WorkspaceUpdateRequest,
    SharedAgentGrantRequest,
    SharedAgentRevokeRequest,
)
from app.services.enterprise import EnterpriseError, get_enterprise_manager
from app.services.enterprise.shared_agents import SharedAgentError, shared_agent_manager

router = APIRouter()


def _authorize(token: str | None, authorization: str | None) -> None:
    try:
        if authorization and authorization.startswith("Bearer "):
            get_enterprise_manager().require_session(authorization[len("Bearer ") :].strip())
        else:
            get_enterprise_manager().require_admin(token)
    except EnterpriseError as exc:
        message = str(exc)
        code = 503 if "locked" in message else 401
        raise HTTPException(status_code=code, detail=message) from exc


def _workspace_response(workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        created_at=datetime.fromisoformat(workspace.created_at),
        updated_at=datetime.fromisoformat(workspace.updated_at),
    )


def _member_response(member) -> MemberResponse:
    return MemberResponse(
        id=member.id,
        display_name=member.display_name,
        role=member.role,
        status=member.status,
        created_at=datetime.fromisoformat(member.created_at),
        updated_at=datetime.fromisoformat(member.updated_at),
    )


def _policy_response(policy) -> PolicyResponse:
    return PolicyResponse(
        key=policy.key,
        enabled=policy.enabled,
        updated_at=datetime.fromisoformat(policy.updated_at),
    )


@router.post("/shared-agents/grants")
def grant_shared_agent(
    request: SharedAgentGrantRequest,
    x_elysia_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    token = authorization[len("Bearer ") :].strip() if authorization and authorization.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Bearer session is required for shared-agent grants")
    try:
        return {"status": "granted", "grant": shared_agent_manager.grant(token, request.agent_id, request.member_id, request.capabilities)}
    except (SharedAgentError, EnterpriseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/shared-agents/grants")
def list_shared_agent_grants(
    agent_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    token = authorization[len("Bearer ") :].strip() if authorization and authorization.startswith("Bearer ") else ""
    try:
        return {"status": "ok", "grants": shared_agent_manager.list(token, agent_id)}
    except (SharedAgentError, EnterpriseError) as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/shared-agents/grants/revoke")
def revoke_shared_agent_grant(
    request: SharedAgentRevokeRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    token = authorization[len("Bearer ") :].strip() if authorization and authorization.startswith("Bearer ") else ""
    try:
        shared_agent_manager.revoke(token, request.grant_id)
        return {"status": "revoked"}
    except (SharedAgentError, EnterpriseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status", response_model=EnterpriseStatusResponse)
def enterprise_status(x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> EnterpriseStatusResponse:
    _authorize(x_elysia_admin_token, authorization)
    value = get_enterprise_manager().status()
    return EnterpriseStatusResponse(
        enabled=value["enabled"],
        workspace=_workspace_response(value["workspace"]),
        member_count=value["member_count"],
        analytics_opt_in=value["analytics_opt_in"],
        admin_auth_configured=value["admin_auth_configured"],
    )


@router.get("/workspace", response_model=WorkspaceResponse)
def workspace(x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> WorkspaceResponse:
    _authorize(x_elysia_admin_token, authorization)
    return _workspace_response(get_enterprise_manager().get_workspace())


@router.patch("/workspace", response_model=WorkspaceResponse)
def update_workspace(request: WorkspaceUpdateRequest, x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> WorkspaceResponse:
    _authorize(x_elysia_admin_token, authorization)
    try:
        return _workspace_response(get_enterprise_manager().update_workspace(request.name))
    except EnterpriseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/members", response_model=MemberListResponse)
def list_members(x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> MemberListResponse:
    _authorize(x_elysia_admin_token, authorization)
    return MemberListResponse(members=[_member_response(item) for item in get_enterprise_manager().list_members()])


@router.post("/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(request: MemberCreateRequest, x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> MemberResponse:
    _authorize(x_elysia_admin_token, authorization)
    try:
        return _member_response(get_enterprise_manager().add_member(request.display_name, request.role))
    except EnterpriseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/members/{member_id}", response_model=MemberResponse)
def update_member(member_id: str, request: MemberUpdateRequest, x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> MemberResponse:
    _authorize(x_elysia_admin_token, authorization)
    try:
        return _member_response(get_enterprise_manager().update_member(member_id, role=request.role, status=request.status))
    except EnterpriseError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: str, x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> None:
    _authorize(x_elysia_admin_token, authorization)
    try:
        get_enterprise_manager().delete_member(member_id)
    except EnterpriseError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("/policies", response_model=PolicyListResponse)
def list_policies(x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> PolicyListResponse:
    _authorize(x_elysia_admin_token, authorization)
    return PolicyListResponse(policies=[_policy_response(item) for item in get_enterprise_manager().list_policies()])


@router.post("/policies", response_model=PolicyResponse)
def update_policy(request: PolicyUpdateRequest, x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> PolicyResponse:
    _authorize(x_elysia_admin_token, authorization)
    try:
        return _policy_response(get_enterprise_manager().set_policy(request.key, request.enabled))
    except EnterpriseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit/summary", response_model=AuditSummaryResponse)
def audit_summary(x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> AuditSummaryResponse:
    _authorize(x_elysia_admin_token, authorization)
    value = get_enterprise_manager().audit_summary()
    return AuditSummaryResponse(
        events=[AuditEventCount(**item) for item in value["events"]],
        recent=[AuditRecentEvent(action=item["action"], status=item["status"], created_at=datetime.fromisoformat(item["created_at"])) for item in value["recent"]],
        retention_days=value["retention_days"],
    )


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(x_elysia_admin_token: str | None = Header(default=None), authorization: str | None = Header(default=None)) -> AnalyticsResponse:
    _authorize(x_elysia_admin_token, authorization)
    value = get_enterprise_manager().analytics()
    return AnalyticsResponse(
        enabled=value["enabled"],
        events=[AnalyticsEvent(event=item["event"], count=item["count"], first_at=datetime.fromisoformat(item["first_at"]), last_at=datetime.fromisoformat(item["last_at"])) for item in value["events"]],
    )
