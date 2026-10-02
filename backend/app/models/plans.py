"""Pydantic schemas for the Phase 8 planning API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ActionClass = Literal["analysis", "local_reversible", "external_side_effect"]


class PlanTaskRequest(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=2000)
    description: str = Field(default="", max_length=2000)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    action_class: ActionClass = "analysis"
    tool_name: str | None = Field(default=None, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = Field(default=0, ge=0, le=5)
    reasoning_summary: str = Field(default="", max_length=2000)


class PlanCreateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    tasks: list[PlanTaskRequest] = Field(min_length=1, max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    risks: list[str] = Field(default_factory=list, max_length=50)
    reasoning_summary: str = Field(default="", max_length=2000)


class PlanReviseRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=2000)
    reasoning_summary: str | None = Field(default=None, max_length=2000)


class PlanDecomposeRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


class PlanTaskResultRequest(BaseModel):
    success: bool
    output: Any = None
    error: str | None = Field(default=None, max_length=2000)
