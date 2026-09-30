"""Pydantic schemas for the Phase 9 autonomous-agent API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentBudgetRequest(BaseModel):
    max_runs: int = Field(default=100, ge=1, le=10000)
    max_runtime_seconds: int = Field(default=120, ge=5, le=3600)
    max_tool_calls_per_run: int = Field(default=10, ge=1, le=100)
    max_browser_requests_per_run: int = Field(default=10, ge=0, le=100)
    max_file_operations_per_run: int = Field(default=10, ge=0, le=100)
    max_notifications_per_day: int = Field(default=10, ge=0, le=100)


class AgentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=2000)
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)
    allowed_plugins: list[str] = Field(default_factory=list, max_length=100)
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)
    allowed_roots: list[str] = Field(default_factory=list, max_length=100)
    interval_seconds: int | None = Field(default=None, ge=300, le=86400)
    budget: AgentBudgetRequest = Field(default_factory=AgentBudgetRequest)


class AgentRunRequest(BaseModel):
    force: bool = False


class AgentMonitorRequest(BaseModel):
    kind: str = Field(pattern="^(file|metric)$")
    config: dict[str, object] = Field(default_factory=dict)


class NotificationReadRequest(BaseModel):
    read: bool = True
