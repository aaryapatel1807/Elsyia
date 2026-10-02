"""REST API for Phase 8 local planning and controlled execution preparation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models import (
    PlanCreateRequest,
    PlanDecomposeRequest,
    PlanReviseRequest,
    PlanTaskResultRequest,
)
from app.services.planning import PlanError, PlanTask, plan_manager
from app.services.planning.decomposer import decompose_goal

router = APIRouter()


def _response(payload: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload)


def _plan_payload(plan: Any) -> dict[str, Any]:
    return {"plan": plan.as_dict()}


def _error(exc: PlanError) -> JSONResponse:
    return _response({"status": "failed", "error": str(exc)}, status_code=400)


@router.get("")
async def list_plans() -> JSONResponse:
    return _response({"status": "ok", "plans": plan_manager.list_plans()})


@router.post("/decompose")
async def decompose_plan(request: PlanDecomposeRequest) -> JSONResponse:
    """Return a local-model draft; persistence still requires explicit create/approve calls."""
    try:
        tasks, reasoning = await decompose_goal(request.goal)
        plan_manager.validate_tasks(tasks)
        return _response(
            {
                "status": "draft",
                "goal": request.goal,
                "tasks": [task.as_dict() for task in tasks],
                "reasoning_summary": reasoning,
            }
        )
    except PlanError as exc:
        return _error(exc)


@router.post("/create")
async def create_plan(request: PlanCreateRequest) -> JSONResponse:
    try:
        tasks = [PlanTask(**task.model_dump()) for task in request.tasks]
        plan = plan_manager.create(
            request.goal,
            tasks,
            assumptions=request.assumptions,
            risks=request.risks,
            reasoning_summary=request.reasoning_summary,
        )
        return _response({"status": "created", **_plan_payload(plan)})
    except PlanError as exc:
        return _error(exc)


@router.get("/{plan_id}")
async def get_plan(plan_id: str) -> JSONResponse:
    try:
        plan = plan_manager.get(plan_id)
        return _response({"status": "ok", **_plan_payload(plan), "events": plan_manager.list_events(plan_id)})
    except PlanError as exc:
        return _error(exc)


@router.post("/{plan_id}/approve")
async def approve_plan(plan_id: str) -> JSONResponse:
    try:
        plan = plan_manager.approve(plan_id)
        return _response({"status": "approved", **_plan_payload(plan)})
    except PlanError as exc:
        return _error(exc)


@router.post("/{plan_id}/execute")
async def prepare_plan_execution(plan_id: str) -> JSONResponse:
    try:
        result = plan_manager.prepare_next(plan_id)
        return _response(result)
    except PlanError as exc:
        return _error(exc)


@router.post("/{plan_id}/prepare-parallel")
async def prepare_parallel_execution(plan_id: str) -> JSONResponse:
    try:
        return _response(plan_manager.prepare_parallel(plan_id))
    except PlanError as exc:
        return _error(exc)


@router.post("/{plan_id}/task/{task_id}/result")
async def record_task_result(
    plan_id: str, task_id: str, request: PlanTaskResultRequest
) -> JSONResponse:
    try:
        return _response(
            plan_manager.record_task_result(
                plan_id,
                task_id,
                success=request.success,
                output=request.output,
                error=request.error,
            )
        )
    except PlanError as exc:
        return _error(exc)


@router.post("/{plan_id}/pause")
async def pause_plan(plan_id: str) -> JSONResponse:
    try:
        plan = plan_manager.pause(plan_id)
        return _response({"status": "paused", **_plan_payload(plan)})
    except PlanError as exc:
        return _error(exc)


@router.post("/{plan_id}/cancel")
async def cancel_plan(plan_id: str) -> JSONResponse:
    try:
        plan = plan_manager.cancel(plan_id)
        return _response({"status": "cancelled", **_plan_payload(plan)})
    except PlanError as exc:
        return _error(exc)


@router.post("/{plan_id}/revise")
async def revise_plan(plan_id: str, request: PlanReviseRequest) -> JSONResponse:
    try:
        plan = plan_manager.revise(plan_id, goal=request.goal, reasoning_summary=request.reasoning_summary)
        return _response({"status": "revised", **_plan_payload(plan)})
    except PlanError as exc:
        return _error(exc)
