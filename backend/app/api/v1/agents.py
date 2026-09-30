"""REST API for local autonomous-agent lifecycle and safe run preparation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models import (
    AgentCreateRequest,
    AgentMonitorRequest,
    AgentRunRequest,
    NotificationReadRequest,
)
from app.services.agents import AgentBudget, AgentError, agent_manager
from app.services.agents.monitoring import MonitorError, monitor_manager

router = APIRouter()


def _ok(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload)


def _error(exc: AgentError | MonitorError) -> JSONResponse:
    return _ok({"status": "failed", "error": str(exc)}, 400)


@router.post("/create")
async def create_agent(request: AgentCreateRequest) -> JSONResponse:
    try:
        budget = AgentBudget(**request.budget.model_dump())
        agent = agent_manager.create(
            request.name,
            request.purpose,
            allowed_tools=request.allowed_tools,
            allowed_plugins=request.allowed_plugins,
            allowed_domains=request.allowed_domains,
            allowed_roots=request.allowed_roots,
            interval_seconds=request.interval_seconds,
            budget=budget,
        )
        return _ok({"status": "created", "agent": agent.as_dict()})
    except AgentError as exc:
        return _error(exc)


@router.get("")
async def list_agents() -> JSONResponse:
    return _ok({"status": "ok", "agents": agent_manager.list(), "emergency_stop": agent_manager.emergency_stop_status()})


@router.get("/emergency-stop")
async def emergency_stop_status() -> JSONResponse:
    return _ok({"active": agent_manager.emergency_stop_status()})


@router.post("/emergency-stop")
async def emergency_stop() -> JSONResponse:
    return _ok(agent_manager.emergency_stop())


@router.post("/emergency-stop/clear")
async def clear_emergency_stop() -> JSONResponse:
    return _ok(agent_manager.clear_emergency_stop())


@router.get("/notifications")
async def list_notifications(unread_only: bool = False) -> JSONResponse:
    return _ok({"status": "ok", "notifications": monitor_manager.notifications.list(unread_only=unread_only)})


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, request: NotificationReadRequest) -> JSONResponse:
    if not request.read:
        return _ok({"status": "ignored"})
    return _ok({"status": "read" if monitor_manager.notifications.mark_read(notification_id) else "not_found"})


@router.get("/{agent_id}/monitors")
async def list_monitors(agent_id: str) -> JSONResponse:
    try:
        agent_manager.get(agent_id)
        return _ok({"status": "ok", "monitors": monitor_manager.list(agent_id)})
    except AgentError as exc:
        return _error(exc)


@router.post("/{agent_id}/monitors")
async def create_monitor(agent_id: str, request: AgentMonitorRequest) -> JSONResponse:
    try:
        return _ok({"status": "created", "monitor": monitor_manager.create(agent_id, request.kind, request.config)})
    except (AgentError, MonitorError) as exc:
        return _error(exc)


@router.post("/monitors/evaluate")
async def evaluate_monitors(metrics: dict[str, float] | None = None) -> JSONResponse:
    return _ok({"status": "evaluated", "notifications": monitor_manager.evaluate(metrics)})


@router.get("/{agent_id}")
async def get_agent(agent_id: str) -> JSONResponse:
    try:
        return _ok({"status": "ok", "agent": agent_manager.get(agent_id).as_dict()})
    except AgentError as exc:
        return _error(exc)


@router.get("/{agent_id}/events")
async def agent_events(agent_id: str) -> JSONResponse:
    try:
        agent_manager.get(agent_id)
        return _ok({"status": "ok", "events": agent_manager.events(agent_id)})
    except AgentError as exc:
        return _error(exc)


@router.post("/{agent_id}/start")
async def start_agent(agent_id: str) -> JSONResponse:
    try:
        return _ok({"status": "scheduled", "agent": agent_manager.start(agent_id).as_dict()})
    except AgentError as exc:
        return _error(exc)


@router.post("/{agent_id}/pause")
async def pause_agent(agent_id: str) -> JSONResponse:
    try:
        return _ok({"status": "paused", "agent": agent_manager.pause(agent_id).as_dict()})
    except AgentError as exc:
        return _error(exc)


@router.post("/{agent_id}/stop")
async def stop_agent(agent_id: str) -> JSONResponse:
    try:
        return _ok({"status": "stopped", "agent": agent_manager.stop(agent_id).as_dict()})
    except AgentError as exc:
        return _error(exc)


@router.post("/{agent_id}/run")
async def run_agent(agent_id: str, request: AgentRunRequest) -> JSONResponse:
    try:
        return _ok(agent_manager.prepare_run(agent_id, force=request.force))
    except AgentError as exc:
        return _error(exc)
