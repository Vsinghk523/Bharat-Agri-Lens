"""widen PII columns to hold Fernet ciphertext + add farm_size

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-23

Companion to ``app/common/encryption.py``. The ``EncryptedString``
TypeDecorator wraps PII columns in Fernet symmetric encryption; the
resulting token is ~78 chars larger than the plaintext plus base64
expansion, so the underlying VARCHAR needs to be widened to hold it.
Sizing formula matches the TypeDecorator: ``length * 2 + 128``.

Per-column reasoning:

- ``address`` 200 → 528: street + city + landmark, the longest of
  the PII fields. Keeps headroom for two-line addresses common in
  rural India ("Village X, Post Y, Tehsil Z").
- ``city`` 100 → 328 and ``state`` 50 → 228: short labels, but
  encrypted form still needs the Fernet overhead.
- ``default_crop_interest`` 100 → 328: comma-separated list of crops
  (e.g. "Tomato, Brinjal, Chilli").
- ``farm_size`` (new) → VARCHAR(228): a short label like "2 acres"
  or "1 hectare". Stored as a string because the UI lets farmers
  pick units and we never do arithmetic on it server-side.

We do NOT widen ``user_email`` or ``mobile_no`` — those stay
plaintext because the OTP sign-in flow looks them up by equality.
Fernet's non-determinism (random IV per encryption) would break
both unique constraints and equality lookups on encrypted columns.

Legacy data: existing plaintext rows continue to read back fine
because ``decrypt_value`` falls back to returning the raw string
on InvalidToken. Newly written rows are encrypted. After everyone
re-saves their profile during onboarding, the fallback becomes
dead code.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Widen existing PII columns to fit Fernet ciphertext.
    op.alter_column(
        "users",
        "address",
        existing_type=sa.String(length=200),
        type_=sa.String(length=528),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "city",
        existing_type=sa.String(length=100),
        type_=sa.String(length=328),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "state",
        existing_type=sa.String(length=50),
        type_=sa.String(length=228),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "default_crop_interest",
        existing_type=sa.String(length=100),
        type_=sa.String(length=328),
        existing_nullable=True,
    )

    # New onboarding field — free-form label like "2 acres".
    op.add_column(
        "users",
        sa.Column("farm_size", sa.String(length=228), nullable=True),
    )


def downgrade() -> None:
    # Drop the new column first so the type-narrow doesn't have to
    # consider it.
    op.drop_column("users", "farm_size")

    # NOTE: narrowing these columns back down is destructive if any
    # rows now hold encrypted (longer) values. The downgrade exists
    # for symmetry but should not be run against a production DB
    # that has already been written to under the new schema.
    op.alter_column(
        "users",
        "default_crop_interest",
        existing_type=sa.String(length=328),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "state",
        existing_type=sa.String(length=228),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "city",
        existing_type=sa.String(length=328),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "address",
        existing_type=sa.String(length=528),
        type_=sa.String(length=200),
        existing_nullable=True,
    )
