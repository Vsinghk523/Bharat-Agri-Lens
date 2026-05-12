from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    user_name: str | None = Field(None, max_length=100)
    user_email: EmailStr | None = None
    isd_code: str | None = Field(None, min_length=2, max_length=2)
    mobile_no: int | None = None
    address: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=50)
    country: str | None = Field(None, min_length=2, max_length=2)
    user_type: str = "Farmer"
    preferred_language: str = "en-IN"
    default_crop_interest: str | None = None
    geo_lat: Decimal | None = None
    geo_lng: Decimal | None = None


class UserCreate(UserBase):
    consent_version: str | None = None
    referral_source: str | None = None


class UserUpdate(BaseModel):
    user_name: str | None = None
    user_email: EmailStr | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    user_type: str | None = None
    preferred_language: str | None = None
    default_crop_interest: str | None = None
    geo_lat: Decimal | None = None
    geo_lng: Decimal | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    status: str
    add_date: datetime
    modify_date: datetime
    kyc_verified: bool
