"""add fcm_tokens table for push-notification device registry

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-27

Each install of the BharatAgriLens app on Android/iOS gets a unique
Firebase Cloud Messaging registration token. We store one row per
(user, device-token) pair so push triggers can fan-out to all of a
user's devices.

Schema choices:
- Composite primary key on (user_id, token) — same user can have
  multiple devices (phone + tablet); same device can be re-registered
  for a different user (rare, after sign-out + sign-in-as-other).
  The natural key avoids a synthetic surrogate that we'd never
  reference from anywhere else.
- ``platform`` tracks 'android' | 'ios' | 'web' for future trigger
  routing (e.g. some payloads only make sense on mobile).
- ``last_seen_at`` updated on every successful send-attempt; lets
  us purge stale tokens (FCM tokens can silently expire after ~270
  days of inactivity).
- ``failure_count`` increments when FCM returns a permanent error
  (UNREGISTERED, INVALID_ARGUMENT). Three strikes and we soft-delete
  the row so we stop wasting quota on dead tokens.

Indexes:
- PRIMARY KEY covers (user_id, token) lookups.
- ix_fcm_tokens_user_id for "fan-out push to user X's devices".
- ix_fcm_tokens_status for the daily-tip cron's "all active tokens"
  scan (filter by status='Active').
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fcm_tokens",
        sa.Column("user_id", sa.String(10), nullable=False),
        # FCM tokens are 152-180 chars in practice; cap at 512 to be
        # safe against future format changes.
        sa.Column("token", sa.String(512), nullable=False),
        sa.Column("platform", sa.String(10), nullable=False),  # android|ios|web
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default="Active",
        ),  # Active | Stale
        sa.PrimaryKeyConstraint("user_id", "token", name="pk_fcm_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.user_id"], ondelete="CASCADE", name="fk_fcm_tokens_user"
        ),
    )
    op.create_index("ix_fcm_tokens_user_id", "fcm_tokens", ["user_id"])
    op.create_index("ix_fcm_tokens_status", "fcm_tokens", ["status"])


def downgrade() -> None:
    op.drop_index("ix_fcm_tokens_status", table_name="fcm_tokens")
    op.drop_index("ix_fcm_tokens_user_id", table_name="fcm_tokens")
    op.drop_table("fcm_tokens")
