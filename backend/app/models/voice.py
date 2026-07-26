"""
Voice Data Models

Pydantic models for the voice (STT/TTS) API.
"""

from typing import Optional

from pydantic import BaseModel, Field


class TranscribeResponse(BaseModel):
    """Response from the transcription endpoint."""

    text: str = Field(description="Transcribed text")
    language: Optional[str] = Field(default=None, description="Detected/requested language")


class SpeakRequest(BaseModel):
    """Request to synthesize speech from text."""

    text: str = Field(description="Text to speak", min_length=1)

    class Config:
        json_schema_extra = {"example": {"text": "Hello, I'm Elysia."}}
