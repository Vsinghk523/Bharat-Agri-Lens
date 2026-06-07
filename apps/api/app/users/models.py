"""User model.

PII fields here are stored encrypted at rest via the
``EncryptedString`` TypeDecorator (see ``app/common/encryption.py``).
The decision matrix for which columns get encrypted:

- ``user_email`` + ``mobile_no``: **plaintext**. The OTP sign-in flow
  looks these up directly with equality predicates, so they have to
  stay searchable. (Fernet is non-deterministic — two encryptions of
  the same value produce different ciphertexts, which breaks both
  unique indexes and equality lookups.)
- ``address``, ``city``, ``state``, ``default_crop_interest``,
  ``farm_size``: **encrypted**. Free-form PII the farmer enters during
  onboarding. Never queried by value.
- ``geo_lat`` / ``geo_lng``: kept as ``Numeric`` because they're
  occasionally used for radius queries; lat/lng on its own without
  the rest of the address is low-sensitivity.
- ``user_name``: plaintext for now (it's commonly shown in the UI and
  rarely uniquely identifying — most farmers share a first name). We
  can promote it to ``EncryptedString`` later without a data
  migration since the ``EncryptedString.process_result_value`` path
  returns legacy plaintext unchanged.
"""
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, CHAR, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import AuditMixin, Base
from app.common.encryption import EncryptedString


class User(AuditMixin, Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    user_name: Mapped[str | None] = mapped_column(String(100))
    user_email: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)

    isd_code: Mapped[str | None] = mapped_column(CHAR(2), nullable=True)
    mobile_no: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )

    # PII — encrypted at rest. The plaintext length passed to
    # EncryptedString matches the previous VARCHAR width so the API
    # contract (max length the UI can submit) doesn't change; the
    # underlying DB column is widened by migration 0005 to hold the
    # Fernet ciphertext.
    address: Mapped[str | None] = mapped_column(EncryptedString(200))
    city: Mapped[str | None] = mapped_column(EncryptedString(100))
    state: Mapped[str | None] = mapped_column(EncryptedString(50))
    country: Mapped[str | None] = mapped_column(CHAR(2))

    user_type: Mapped[str] = mapped_column(String(20), default="Farmer")
    # Auth role. "user" for end users, "admin" for staff who can view
    # the labelling queue + hard-delete other users. Keep this single-
    # column string instead of a separate roles table — we have one
    # axis of privilege right now.
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)

    preferred_language: Mapped[str] = mapped_column(CHAR(5), default="en-IN")
    kyc_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(10))
    referral_source: Mapped[str | None] = mapped_column(String(50))

    # Onboarding fields — both encrypted because they're free-form PII
    # we never query by value. ``farm_size`` is a short label like
    # "2 acres" or "1 hectare"; we store it as a string instead of a
    # number because the UI lets the farmer pick units and we don't
    # need to do arithmetic on it server-side.
    default_crop_interest: Mapped[str | None] = mapped_column(EncryptedString(100))
    farm_size: Mapped[str | None] = mapped_column(EncryptedString(50))

    geo_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    geo_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    # 6-digit Indian pincode. Captured during onboarding for Trigger #3
    # (hyperlocal outbreak alerts). Optional — onboarding lets users
    # skip. Deliberately PLAINTEXT (not EncryptedString) because the
    # outbreak-detection cron filters by pincode in SQL, and Fernet's
    # non-deterministic encryption would break that. Pincode alone is
    # low-sensitivity — thousands of farmers share each pincode.
    pincode: Mapped[str | None] = mapped_column(CHAR(6), nullable=True, index=True)

    # User-level toggles (notification preferences, privacy choices).
    # Defaults are filled in by ``UserPreferences`` Pydantic schema at
    # read time so unknown keys on existing rows behave correctly.
    # See ``app/users/schemas.py::UserPreferences`` for the canonical
    # shape and defaults.
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
