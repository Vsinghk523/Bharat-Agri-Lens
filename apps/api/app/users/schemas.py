from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPreferences(BaseModel):
    """User-level preference toggles.

    Stored as a JSONB blob on ``users.preferences``. This schema is the
    canonical source of truth for which preferences exist and what
    their defaults are — unknown keys in the DB are ignored, missing
    keys take their default value. That gives us free "schema
    evolution": adding a new toggle in a release means appending a
    field here, no migration required.

    Grouping (purely organisational, all in the same JSONB):
    - ``notif_*``: which push categories the user wants to receive
    - ``privacy_*``: data-sharing choices

    All booleans default to a sensible "on for benefit, off for
    spammy" stance:
    - Diagnosis updates (high-signal, user-initiated)         → on
    - Weather / pest pressure alerts (medium signal, region)  → on
    - Daily morning tips (potentially noisy)                  → off
    - Article digests (low signal, weekly)                    → off
    - Anonymous-data sharing (helps the model improve)        → on
    """

    notif_diagnoses: bool = True
    notif_weather: bool = True
    notif_daily_tip: bool = False
    notif_articles: bool = False
    # Treatment-reminder push for diagnoses with a recurring spray
    # cycle (fungal, bacterial, insect_pest, nematode, nutrient
    # deficiency). Default on — the value of these reminders is high
    # and the cadence is bounded (3 per diagnosis).
    notif_treatment_reminders: bool = True
    # Hyperlocal outbreak alert when >=5 farmers in this user's pincode
    # report the same disease in a 7-day window. Default on for the
    # warning value; user can opt out in Settings if they don't want
    # area-level alerts.
    notif_outbreak_alerts: bool = True
    privacy_share_anonymous_data: bool = True

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "UserPreferences":
        """Build from the raw JSONB dict, dropping unknown keys."""
        if not raw:
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.model_fields}
        return cls(**known)


class UserBase(BaseModel):
    user_name: str | None = Field(None, max_length=100)
    user_email: EmailStr | None = None
    isd_code: str | None = Field(None, min_length=2, max_length=2)
    mobile_no: int | None = None
    address: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=50)
    country: str | None = Field(None, min_length=2, max_length=2)
    pincode: str | None = Field(
        None, min_length=6, max_length=6, pattern=r"^\d{6}$"
    )
    user_type: str = "Farmer"
    preferred_language: str = "en-IN"
    default_crop_interest: str | None = Field(None, max_length=100)
    farm_size: str | None = Field(None, max_length=50)
    geo_lat: Decimal | None = None
    geo_lng: Decimal | None = None


class UserCreate(UserBase):
    consent_version: str | None = None
    referral_source: str | None = None


class UserUpdate(BaseModel):
    """Partial update used by ``PATCH /users/me``.

    All fields optional; the onboarding wizard sends a subset on each
    step (location step sends city/state/country, farm step sends
    farm_size/default_crop_interest, etc.). Lengths mirror UserBase so
    we reject oversize input at the edge before encryption.
    """

    user_name: str | None = Field(None, max_length=100)
    user_email: EmailStr | None = None
    address: str | None = Field(None, max_length=200)
    city: str | None = Field(None, max_length=100)
    state: str | None = Field(None, max_length=50)
    country: str | None = Field(None, min_length=2, max_length=2)
    pincode: str | None = Field(
        None, min_length=6, max_length=6, pattern=r"^\d{6}$"
    )
    user_type: str | None = None
    preferred_language: str | None = None
    default_crop_interest: str | None = Field(None, max_length=100)
    farm_size: str | None = Field(None, max_length=50)
    geo_lat: Decimal | None = None
    geo_lng: Decimal | None = None


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    status: str
    add_date: datetime
    modify_date: datetime
    kyc_verified: bool
    role: str
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class PreferencesUpdate(BaseModel):
    """Partial update for ``users.preferences``.

    Every field is optional; only the keys present in the request body
    are merged into the stored JSONB. Mirrors ``UserPreferences`` field
    by field so the OpenAPI schema makes the contract explicit.
    """

    notif_diagnoses: bool | None = None
    notif_weather: bool | None = None
    notif_daily_tip: bool | None = None
    notif_articles: bool | None = None
    notif_treatment_reminders: bool | None = None
    notif_outbreak_alerts: bool | None = None
    privacy_share_anonymous_data: bool | None = None
