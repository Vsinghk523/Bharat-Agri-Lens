import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from jose import jwt

from app.config import get_settings
from app.logging import get_logger

settings = get_settings()
log = get_logger(__name__)


def generate_otp(digits: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(digits))


def hash_otp(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


def issue_tokens(user_id: str) -> tuple[str, str]:
    now = datetime.now(UTC)
    access_payload = {
        "sub": user_id,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_ttl_min)).timestamp()),
    }
    refresh_payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_refresh_ttl_days)).timestamp()),
    }
    access = jwt.encode(access_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    refresh = jwt.encode(refresh_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return access, refresh


async def send_otp_email(email: str, code: str) -> bool:
    if not settings.resend_api_key:
        if settings.environment != "production":
            log.warning(
                "dev_otp_email",
                email=email,
                code=code,
                note="Resend not configured; printing OTP for dev only",
            )
            return True
        log.warning("resend_not_configured", email=email)
        return False
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.otp_email_from,
                "to": [email],
                "subject": "Your BharatAgriLens code",
                "text": f"Your verification code is: {code}. It expires in 5 minutes.",
            },
        )
        return resp.status_code < 400


async def send_otp_whatsapp(isd_code: str, mobile_no: int, code: str) -> bool:
    if not (settings.whatsapp_phone_number_id and settings.whatsapp_access_token):
        if settings.environment != "production":
            log.warning(
                "dev_otp_whatsapp",
                mobile=mobile_no,
                isd_code=isd_code,
                code=code,
                note="WhatsApp not configured; printing OTP for dev only",
            )
            return True
        log.warning("whatsapp_not_configured", mobile=mobile_no)
        return False
    url = f"https://graph.facebook.com/v21.0/{settings.whatsapp_phone_number_id}/messages"
    to_number = f"{isd_code}{mobile_no}"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": settings.whatsapp_otp_template_name,
            "language": {"code": settings.whatsapp_otp_template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": code}],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": code}],
                },
            ],
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            json=payload,
        )
        return resp.status_code < 400
