"""Pydantic models for tool catalog and direct execution APIs."""

from typing import Any

from pydantic import BaseModel, Field


class ToolExecuteRequest(BaseModel):
    """Request to execute a registered tool."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = Field(default=False)


class ToolCatalogResponse(BaseModel):
    """Registered tool metadata."""

    tools: list[dict[str, Any]]
