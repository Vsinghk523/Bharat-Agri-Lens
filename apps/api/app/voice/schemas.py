from typing import Literal

from pydantic import BaseModel, Field


class SttRequest(BaseModel):
    # Base64 of the audio bytes. Cap at ~7 MiB raw which is more than
    # enough for a 30-second speech sample at typical bitrates.
    audio_b64: str = Field(..., max_length=10_000_000)
    language: str = Field(default="en-IN", description="BCP-47, e.g. hi-IN")


class SttResponse(BaseModel):
    transcript: str
    language: str
    provider: Literal["bhashini", "mock"]


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    language: str = Field(default="en-IN")
    gender: Literal["female", "male"] = "female"


class TtsResponse(BaseModel):
    audio_b64: str
    mime_type: str
    language: str
    provider: Literal["bhashini", "mock"]
