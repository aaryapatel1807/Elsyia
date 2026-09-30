"""Pydantic schemas for the Phase 4 plugin API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PluginCatalogResponse(BaseModel):
    plugins: list[dict[str, Any]]


class PluginToggleRequest(BaseModel):
    confirmed: bool = False


class PluginExecuteRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
