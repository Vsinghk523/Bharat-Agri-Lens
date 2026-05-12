import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatSessionCreate(BaseModel):
    title: str | None = None
    language: str = "en-IN"


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    user_id: str
    title: str | None
    language: str
    status: str
    add_date: datetime


class ChatMessageCreate(BaseModel):
    """Client-side input for POST /chat/messages.

    ``session_id`` is optional — when omitted the API creates a fresh
    session for the user on the fly. ``role`` is not exposed: the
    server stamps it as 'user'.
    """

    session_id: uuid.UUID | None = None
    language: str = "en-IN"
    content_text: str = Field(..., min_length=1, max_length=2000)


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: uuid.UUID
    session_id: uuid.UUID
    role: str
    language: str
    content_text: str | None
    audio_blob_url: str | None
    transcription: str | None
    add_date: datetime


class ChatExchange(BaseModel):
    """Round trip from POST /chat/messages: the user bubble + the
    assistant bubble in one response so the client can render both at
    once. ``assistant_message`` is null when the inference service is
    unreachable; ``error`` carries a short diagnostic in that case."""

    session_id: uuid.UUID
    user_message: ChatMessageRead
    assistant_message: ChatMessageRead | None = None
    error: str | None = None
