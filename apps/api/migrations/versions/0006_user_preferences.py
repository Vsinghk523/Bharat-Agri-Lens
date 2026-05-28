"""add users.preferences JSONB column with defaults

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-27

The Settings page exposes a small set of user-level toggles
(notification categories, anonymous-data sharing). Until now those
were React local state that vanished on refresh. This migration adds
a single ``preferences`` JSONB column on the users table; the API
layer treats unknown keys as missing and folds in defaults at read
time, so new toggles in future releases ship without a migration.

Why JSONB and not a separate user_preferences table:
- The toggle set is small (<20) and flat — no relational structure.
- We frequently want to read the user *and* their prefs together
  (e.g. when sending push: "is notif_diagnoses on?"). JSONB keeps
  this a single row read.
- Adding a new toggle means updating a Pydantic model, not running
  a migration. Velocity matters here; the data shape is stable
  enough that we don't gain much from per-column typing.

Default values: ``{}`` (empty object). The Pydantic schema layers
the defaults on top so existing rows behave as if every toggle is
at its default value.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
