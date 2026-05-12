from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class OtpRequest(BaseModel):
    channel: Literal["email", "whatsapp"]
    email: EmailStr | None = None
    isd_code: str | None = Field(None, min_length=2, max_length=2)
    mobile_no: int | None = None


class OtpRequestResponse(BaseModel):
    delivery_id: str
    expires_in_seconds: int
    channel: str


class OtpVerify(BaseModel):
    channel: Literal["email", "whatsapp"]
    email: EmailStr | None = None
    mobile_no: int | None = None
    code: str = Field(..., min_length=4, max_length=8)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str


class ConsentAccept(BaseModel):
    consent_version: str = Field(..., min_length=1, max_length=10)
