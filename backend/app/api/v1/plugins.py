"""REST API for trusted local plugins."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.models import PluginCatalogResponse, PluginExecuteRequest, PluginToggleRequest
from app.services.plugins import PluginError, plugin_manager
from app.services.tools.audit import record_tool_event

router = APIRouter()


def _result_dict(result: Any) -> dict[str, Any]:
    return {
        "status": result.status,
        "tool_name": result.tool_name,
        "result": result.result,
        "error": result.error,
        "confirmation_required": result.confirmation_required,
        "confirmation_message": result.confirmation_message,
        "metadata": result.metadata,
    }


@router.get("", response_model=PluginCatalogResponse)
@router.get("/", response_model=PluginCatalogResponse, include_in_schema=False)
def list_plugins() -> PluginCatalogResponse:
    """List discovered plugin metadata and lifecycle state."""
    return PluginCatalogResponse(plugins=plugin_manager.list())


@router.post("/refresh")
async def refresh_plugins() -> dict[str, Any]:
    """Rediscover trusted local plugin manifests without restarting the backend."""
    plugin_manager.refresh(auto_enable=True)
    return {"status": "refreshed", "plugins": plugin_manager.list()}


@router.post("/{plugin_id}/enable")
async def enable_plugin(
    plugin_id: str,
    request: PluginToggleRequest | None = None,
) -> dict[str, Any]:
    """Enable a trusted plugin; risky permission declarations require confirmation."""
    record = plugin_manager.get(plugin_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    confirmed = bool(request and request.confirmed)
    if record.manifest.requires_confirmation and not confirmed:
        return {
            "status": "confirmation_required",
            "plugin_id": plugin_id,
            "confirmation_required": True,
            "confirmation_message": "Confirm enabling this plugin because it requests protected permissions.",
        }
    try:
        enabled = plugin_manager.enable(plugin_id)
    except PluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "enabled", "plugin": enabled.as_dict()}


@router.post("/{plugin_id}/disable")
async def disable_plugin(plugin_id: str) -> dict[str, Any]:
    """Disable a plugin and unregister its tools without deleting its files."""
    try:
        disabled = plugin_manager.disable(plugin_id)
    except PluginError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "disabled", "plugin": disabled.as_dict()}


@router.post("/{plugin_id}/execute")
async def execute_plugin(plugin_id: str, request: PluginExecuteRequest) -> dict[str, Any]:
    """Execute one enabled plugin tool through the shared permission registry."""
    result = await plugin_manager.execute(
        plugin_id,
        request.tool,
        request.arguments,
        confirmed=request.confirmed,
    )
    result_dict = _result_dict(result)
    record_tool_event(
        tool_name=f"plugin.{plugin_id}.{request.tool}",
        status=result.status,
        arguments=request.arguments,
        result=result_dict,
    )
    return {"plugin_id": plugin_id, **result_dict}
