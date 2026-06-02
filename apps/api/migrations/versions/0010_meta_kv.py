"""add meta_kv key-value table for small bits of operational state

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-29

Why a table instead of an env var or a JSON file:
- Persists across deploys (env vars get clobbered, /tmp gets wiped).
- Doesn't require any new infrastructure (Redis, ConfigCat, etc.) for
  what is genuinely just a few rows of "remember when X last ran".
- Cheap atomic compare-and-set via UPDATE ... RETURNING.

Initial users:
- ``training_export.last_export_at`` — the timestamp the most recent
  export job ran. Picked up by the next run to filter "what's new
  since last time".

Anything that wants to scribble a small piece of cron / job state
should land here rather than carving a dedicated table.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meta_kv",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("meta_kv")
