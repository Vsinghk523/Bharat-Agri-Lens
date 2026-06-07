"""SQLAlchemy models for treatment_reminders + outbreak_alerts.

See migration 0011 for the schema reasoning. Briefly:

- ``TreatmentReminder``: per-diagnosis scheduled push. Created in
  triplicate at diagnosis time (one row per step in the spray cycle).
  Hourly cron picks pending+due rows and fires the FCM notification.

- ``OutbreakAlert``: dedup tracker. Stops the daily outbreak-detection
  cron from notifying the same user about the same outbreak twice.
"""
import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base


class TreatmentReminder(Base):
    __tablename__ = "treatment_reminders"

    reminder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    diagnostic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plant_diagnostics.diagnostic_id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    # Step number within this diagnosis's reminder cycle (1, 2, 3 by
    # default). Combined with diagnostic_id forms the unique key.
    step_no: Mapped[int] = mapped_column(Integer)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # pending | sent | failed | dismissed
    status: Mapped[str] = mapped_column(String(10), default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("diagnostic_id", "step_no", name="uq_treatment_reminders_diag_step"),
    )


class OutbreakAlert(Base):
    __tablename__ = "outbreak_alerts"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("users.user_id", ondelete="CASCADE")
    )
    pincode: Mapped[str] = mapped_column(CHAR(6))
    infection_type: Mapped[str] = mapped_column(String(30))
    # ISO week key like "2026-W23" — coarse enough that a 7-day rolling
    # outbreak doesn't re-fire if detected on consecutive days.
    week_key: Mapped[str] = mapped_column(String(8))
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_count: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "pincode",
            "infection_type",
            "week_key",
            name="uq_outbreak_alerts_dedup",
        ),
    )
