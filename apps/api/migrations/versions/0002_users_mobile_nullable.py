"""make users.mobile_no and users.isd_code nullable

Email-only signups (Resend channel) should not require a phone number.
Mobile remains UNIQUE — NULLs do not collide under that constraint.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "mobile_no", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("users", "isd_code", existing_type=sa.CHAR(2), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "isd_code", existing_type=sa.CHAR(2), nullable=False)
    op.alter_column("users", "mobile_no", existing_type=sa.BigInteger(), nullable=False)
