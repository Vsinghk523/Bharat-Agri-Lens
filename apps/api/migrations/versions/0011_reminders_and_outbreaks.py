"""add pincode, treatment_reminders, outbreak_alerts

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-02

Three changes for Trigger #2 (treatment reminders) + Trigger #3
(hyperlocal outbreak alerts):

1. ``users.pincode`` (CHAR(6))
   6-digit Indian pincode captured during onboarding. Optional —
   existing users get NULL. Used by Trigger #3's audience filter:
   "5+ reports of disease X in pincode 411001 in the last 7 days →
   notify everyone in 411001 who hasn't already reported".

   Pincode encryption: deliberately PLAINTEXT, not EncryptedString.
   Trigger #3's detection query has to filter by pincode in SQL, and
   Fernet's non-deterministic encryption breaks any equality query.
   Pincode alone is low-sensitivity (6 digits covers thousands of
   farmers per pincode) and we don't store it alongside name +
   address as a free-text PII bundle.

2. ``treatment_reminders``
   One row per scheduled push to a user about a diagnosis. The
   inserter (diagnostics router) schedules 3 rows per diagnosis at
   infection-type-specific intervals. An hourly cron picks up rows
   where ``scheduled_at <= now() AND status='pending' AND
   dismissed_at IS NULL`` and fires push via the FCM service.

   ``status`` lifecycle: pending → sent (success), pending → failed
   (FCM error after 3 retries), pending → dismissed (user tapped
   Cancel on the Result page).

3. ``outbreak_alerts``
   Dedup table for Trigger #3. One row per (user, pincode,
   infection_type, week-of-year). Inserted when we notify a user
   about an outbreak; the daily detection cron uses
   ``ON CONFLICT DO NOTHING`` to avoid re-notifying about the same
   outbreak more than once per week.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. pincode on users
    op.add_column("users", sa.Column("pincode", sa.CHAR(6), nullable=True))
    op.create_index("ix_users_pincode", "users", ["pincode"])

    # 2. treatment_reminders
    op.create_table(
        "treatment_reminders",
        sa.Column("reminder_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("diagnostic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(10), nullable=False),
        # Sequence within a diagnosis: 1 = first reminder, 2 = second, etc.
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(10), nullable=False, server_default="pending"
        ),  # pending | sent | failed | dismissed
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["diagnostic_id"],
            ["plant_diagnostics.diagnostic_id"],
            ondelete="CASCADE",
            name="fk_treatment_reminders_diagnostic",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
            name="fk_treatment_reminders_user",
        ),
        sa.UniqueConstraint(
            "diagnostic_id", "step_no", name="uq_treatment_reminders_diag_step"
        ),
    )
    # The cron processor's filter: pick pending reminders due now.
    # Partial index on status='pending' since the table will accumulate
    # sent rows over time and we only ever scan the pending subset.
    op.create_index(
        "ix_treatment_reminders_due",
        "treatment_reminders",
        ["scheduled_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_treatment_reminders_diagnostic",
        "treatment_reminders",
        ["diagnostic_id"],
    )

    # 3. outbreak_alerts (dedup tracker)
    op.create_table(
        "outbreak_alerts",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(10), nullable=False),
        sa.Column("pincode", sa.CHAR(6), nullable=False),
        sa.Column("infection_type", sa.String(30), nullable=False),
        # ISO 8601 week of the outbreak detection (e.g. "2026-W23"). Lets us
        # express "same outbreak window" without dragging in date ranges.
        sa.Column("week_key", sa.String(8), nullable=False),
        sa.Column(
            "notified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # How many reports underlay this alert at detection time, for audit.
        sa.Column("report_count", sa.Integer, nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
            name="fk_outbreak_alerts_user",
        ),
        sa.UniqueConstraint(
            "user_id",
            "pincode",
            "infection_type",
            "week_key",
            name="uq_outbreak_alerts_dedup",
        ),
    )


def downgrade() -> None:
    op.drop_table("outbreak_alerts")
    op.drop_index("ix_treatment_reminders_diagnostic", table_name="treatment_reminders")
    op.drop_index("ix_treatment_reminders_due", table_name="treatment_reminders")
    op.drop_table("treatment_reminders")
    op.drop_index("ix_users_pincode", table_name="users")
    op.drop_column("users", "pincode")
