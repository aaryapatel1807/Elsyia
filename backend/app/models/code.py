"""Pydantic schemas for the Phase 7 read-only code assistant API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CodeRootRequest(BaseModel):
    root: str | None = Field(default=None, max_length=2048)


class CodeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    mode: Literal["text", "path", "symbol"] = "text"
    root: str | None = Field(default=None, max_length=2048)
