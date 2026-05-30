"""add plant_diagnostics.prediction_source column

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-29

Companion to the Gemini LLM-fallback layer in
services/inference/app/llm_fallback.py.

Values:
- ``plantvit``      : our trained specialist model (the normal path)
- ``llm_fallback``  : Gemini was used because our model rejected
                      with non_target_plant / low_confidence /
                      ambiguous
- ``mock``          : the in-process mock predictor (dev / CI)

Default ``plantvit`` rather than NULL — every existing row was
produced by the real predictor, and a non-null column makes filter
queries simpler ("show me everything that wasn't the specialist").

No index: the column will be used for analytics queries (counts
grouped by source, daily quota tallies), which run fine without one
at our scale. The per-user daily quota query in the API:

    SELECT COUNT(*) FROM plant_diagnostics
    WHERE user_id = $1
      AND prediction_source = 'llm_fallback'
      AND add_date >= CURRENT_DATE

is already fast thanks to the existing user_id + add_date indexes.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plant_diagnostics",
        sa.Column(
            "prediction_source",
            sa.String(length=20),
            nullable=False,
            server_default="plantvit",
        ),
    )


def downgrade() -> None:
    op.drop_column("plant_diagnostics", "prediction_source")
