"""REST API for local repository indexing and read-only code analysis."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.models import CodeRootRequest, CodeSearchRequest
from app.services.tools import registry
from app.services.tools.audit import record_tool_event

router = APIRouter()


def _payload(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "tool_name": result.tool_name,
        "result": result.result,
        "error": result.error,
        "confirmation_required": result.confirmation_required,
        "confirmation_message": result.confirmation_message,
        "metadata": result.metadata,
    }


async def _execute(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await registry.execute(tool_name, arguments, confirmed=False)
    payload = _payload(result)
    record_tool_event(tool_name=tool_name, status=result.status, arguments=arguments, result=payload)
    return payload


@router.post("/index")
async def index_repository(request: CodeRootRequest) -> dict[str, Any]:
    return await _execute("index_code_repository", {"root": request.root})


@router.post("/analyze")
async def analyze_repository(request: CodeRootRequest) -> dict[str, Any]:
    return await _execute("analyze_code_repository", {"root": request.root})


@router.post("/search")
async def search_repository(request: CodeSearchRequest) -> dict[str, Any]:
    return await _execute(
        "search_code_repository",
        {"query": request.query, "mode": request.mode, "root": request.root},
    )


@router.get("/status")
async def code_status() -> dict[str, Any]:
    return await _execute("code_repository_status", {})
