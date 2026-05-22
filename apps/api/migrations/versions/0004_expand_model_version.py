"""expand plant_diagnostics.model_version to fit real predictor versions

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-22

The original VARCHAR(50) was sized for the mock predictor's terse
version string (e.g. ``api-inline-mock-0.1``). The real ONNX predictor
emits ``<config-name>-<backbone-with-slashes-replaced>``, which for the
v0 release evaluates to:

    plantvit-v0-plantvillage-google_vit-base-patch16-224     (52 chars)

Two characters over the limit → every INSERT from real-predictor mode
blew up with StringDataRightTruncationError on the first try. Bump the
column to VARCHAR(128) which comfortably fits anything we'd reasonably
generate: ``<name>-<backbone>-<adapter_tag>`` is still well under that.

We leave the ``model_artifacts.model_version`` column (a related but
distinct entity tracking model registry rows) at VARCHAR(50) — that
field stores semver-ish identifiers entered by humans, not derived
strings, so the 50-char ceiling is still appropriate there.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "plant_diagnostics",
        "model_version",
        existing_type=sa.String(length=50),
        type_=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "plant_diagnostics",
        "model_version",
        existing_type=sa.String(length=128),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
