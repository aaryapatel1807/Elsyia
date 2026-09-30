"""Tool catalog and direct execution endpoints."""

from typing import Any

from fastapi import APIRouter

from app.models import ToolCatalogResponse, ToolExecuteRequest
from app.services.tools import registry
from app.services.tools.audit import record_tool_event

router = APIRouter()


@router.get("/", response_model=ToolCatalogResponse)
def list_tools() -> ToolCatalogResponse:
    """List tools available to the assistant and their permission policy."""
    return ToolCatalogResponse(tools=registry.list())


@router.post("/{tool_name}")
async def execute_tool(tool_name: str, request: ToolExecuteRequest) -> dict[str, Any]:
    """Execute one registered tool with confirmation enforcement."""
    result = await registry.execute(
        tool_name,
        request.arguments,
        confirmed=request.confirmed,
    )
    result_dict = {
        "status": result.status,
        "tool_name": result.tool_name,
        "result": result.result,
        "error": result.error,
        "confirmation_required": result.confirmation_required,
        "confirmation_message": result.confirmation_message,
        "metadata": result.metadata,
    }
    record_tool_event(
        tool_name=tool_name,
        status=result.status,
        arguments=request.arguments,
        result=result_dict,
    )
    return result_dict
