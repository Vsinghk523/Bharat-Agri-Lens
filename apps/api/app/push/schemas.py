from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["android", "ios", "web"]


class TokenRegister(BaseModel):
    """Mobile-side payload when registering a fresh FCM token.

    Sent on first app launch after the user grants notification
    permission, and any time FCM rotates the token (handled in the
    Capacitor ``pushNotifications.addListener('registration', …)``
    handler).
    """

    token: str = Field(..., min_length=20, max_length=512)
    platform: Platform


class TokenRegisterResponse(BaseModel):
    ok: bool = True
