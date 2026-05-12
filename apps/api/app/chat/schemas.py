import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
    session_id: uuid.UUID
    role: str = "user"
    language: str = "en-IN"
    content_text: str | None = None
    audio_blob_url: str | None = None


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
