"""SQLAlchemy model for the FCM device registry."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base


class FcmToken(Base):
    """One row per (user, device) pair.

    See migration 0007 for the schema reasoning. Briefly:
    - Composite PK on (user_id, token) — natural key, no synthetic id
      needed because nothing else references this table.
    - ``platform`` tells the sender which payload shape to use.
    - ``status``: 'Active' is the only sent-to state; 'Stale' rows
      are kept for analytics but skipped by the sender.
    - ``failure_count`` increments on permanent FCM errors; we mark
      Stale after 3 consecutive failures.
    """

    __tablename__ = "fcm_tokens"

    user_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(512), primary_key=True)
    platform: Mapped[str] = mapped_column(String(10))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="Active", index=True)
