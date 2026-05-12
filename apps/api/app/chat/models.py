import uuid

from sqlalchemy import CHAR, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import AuditMixin, Base


class ChatSession(AuditMixin, Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(10), ForeignKey("users.user_id"), index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(CHAR(5), default="en-IN")


class ChatMessage(AuditMixin, Base):
    __tablename__ = "chat_messages"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.session_id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    language: Mapped[str] = mapped_column(CHAR(5), default="en-IN")
    content_text: Mapped[str | None] = mapped_column(Text)
    audio_blob_url: Mapped[str | None] = mapped_column(String(300))
    transcription: Mapped[str | None] = mapped_column(Text)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
