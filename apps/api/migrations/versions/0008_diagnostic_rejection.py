"""add plant_diagnostics.rejection_reason + rejection_hint columns

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-28

Companion to the OOD defense work in services/inference:

- ``rejection_reason`` carries the structured reason a diagnosis was
  refused — one of (too_blurry, too_dark, too_small, not_a_plant,
  non_target_plant, low_confidence, ambiguous). NULL when the model
  produced a normal diagnosis.
- ``rejection_hint`` is the CLIP gate's best guess at what the image
  *did* look like — used to render messages like "looks like a rose"
  to help the farmer learn what to retake.

Both are nullable so existing rows (and any successful future
diagnoses) are unaffected. We keep them as short strings — 30 chars
covers every reason in the canonical list with room to grow.

No index needed: rejection_reason is a small enum-ish column we'll
query with ``WHERE rejection_reason IS NULL`` for the labelling-queue
view; postgres handles that fine without an index at our scale.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plant_diagnostics",
        sa.Column("rejection_reason", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "plant_diagnostics",
        sa.Column("rejection_hint", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plant_diagnostics", "rejection_hint")
    op.drop_column("plant_diagnostics", "rejection_reason")
