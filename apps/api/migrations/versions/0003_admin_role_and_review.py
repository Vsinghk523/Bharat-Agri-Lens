"""users.role + reviewer correction columns on plant_diagnostics

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13

Adds:
- users.role             VARCHAR(20) NOT NULL DEFAULT 'user'
  Drives /admin/* and DELETE /users/{id}/purge gating. Allowed
  values for now: 'user', 'admin'. Extending later (reviewer,
  support) needs no migration — just config.
- plant_diagnostics.correct_plant            VARCHAR(100)
                  .correct_disease           VARCHAR(150)
                  .correct_infection_type    VARCHAR(30)
                  .reviewed_by               VARCHAR(10) FK users
                  .reviewed_at               TIMESTAMPTZ
  Reviewer's authoritative re-label, used to feed the next
  training run. NULL means "not yet reviewed".
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    op.add_column("plant_diagnostics", sa.Column("correct_plant", sa.String(100)))
    op.add_column("plant_diagnostics", sa.Column("correct_disease", sa.String(150)))
    op.add_column("plant_diagnostics", sa.Column("correct_infection_type", sa.String(30)))
    op.add_column(
        "plant_diagnostics",
        sa.Column("reviewed_by", sa.String(10), sa.ForeignKey("users.user_id")),
    )
    op.add_column(
        "plant_diagnostics",
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_plant_diagnostics_reviewed_by", "plant_diagnostics", ["reviewed_by"])


def downgrade() -> None:
    op.drop_index("ix_plant_diagnostics_reviewed_by", "plant_diagnostics")
    op.drop_column("plant_diagnostics", "reviewed_at")
    op.drop_column("plant_diagnostics", "reviewed_by")
    op.drop_column("plant_diagnostics", "correct_infection_type")
    op.drop_column("plant_diagnostics", "correct_disease")
    op.drop_column("plant_diagnostics", "correct_plant")
    op.drop_index("ix_users_role", "users")
    op.drop_column("users", "role")
