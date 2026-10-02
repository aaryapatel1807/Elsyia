"""Pydantic schemas for the Phase 6 browser foundation API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BrowserNavigateRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class BrowserSessionRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)


class BrowserScreenshotRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)
    confirmed: bool = False


class BrowserDownloadRequest(BaseModel):
    session_id: str = Field(min_length=16, max_length=64)
    url: str = Field(min_length=1, max_length=2048)
    confirmed: bool = False
