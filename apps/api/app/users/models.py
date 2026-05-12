from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CHAR, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import AuditMixin, Base


class User(AuditMixin, Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    user_name: Mapped[str | None] = mapped_column(String(100))
    user_email: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)

    isd_code: Mapped[str] = mapped_column(CHAR(2))
    mobile_no: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    address: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str | None] = mapped_column(CHAR(2))

    user_type: Mapped[str] = mapped_column(String(20), default="Farmer")

    preferred_language: Mapped[str] = mapped_column(CHAR(5), default="en-IN")
    kyc_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(10))
    referral_source: Mapped[str | None] = mapped_column(String(50))
    default_crop_interest: Mapped[str | None] = mapped_column(String(100))
    geo_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    geo_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
