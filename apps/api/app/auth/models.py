import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CHAR, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base


class OtpAttempt(Base):
    __tablename__ = "otp_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mobile_no: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    channel: Mapped[str] = mapped_column(String(20))  # 'email' | 'whatsapp'
    otp_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempt_count: Mapped[int] = mapped_column(default=0)
    delivery_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requester_ip: Mapped[str | None] = mapped_column(String(45))


class ConsentLog(Base):
    __tablename__ = "consent_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(10), index=True)
    consent_version: Mapped[str] = mapped_column(String(10))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
