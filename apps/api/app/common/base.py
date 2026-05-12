from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class AuditMixin:
    """Audit + soft-delete columns shared across business tables."""

    add_user: Mapped[str | None] = mapped_column(String(10), nullable=True)
    add_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    modify_user: Mapped[str | None] = mapped_column(String(10), nullable=True)
    modify_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    status: Mapped[str] = mapped_column(String(10), default="Active", index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
