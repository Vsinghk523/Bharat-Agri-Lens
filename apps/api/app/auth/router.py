import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import ConsentLog, OtpAttempt
from app.auth.schemas import (
    ConsentAccept,
    OtpRequest,
    OtpRequestResponse,
    OtpVerify,
    TokenPair,
)
from app.auth.service import generate_otp, hash_otp, issue_tokens, send_otp_email, send_otp_whatsapp
from app.common.errors import RateLimitError, UnauthorizedError
from app.config import get_settings
from app.db import get_session
from app.logging import get_logger
from app.users.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
log = get_logger(__name__)


def _gen_user_id() -> str:
    return secrets.token_hex(5).upper()


@router.post("/otp/request", response_model=OtpRequestResponse)
async def request_otp(
    payload: OtpRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> OtpRequestResponse:
    if payload.channel == "email" and not payload.email:
        raise UnauthorizedError("Email required for email channel")
    if payload.channel == "whatsapp" and not (payload.mobile_no and payload.isd_code):
        raise UnauthorizedError("Mobile + ISD code required for WhatsApp channel")

    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent_stmt = select(OtpAttempt).where(
        OtpAttempt.created_at > one_hour_ago,
        OtpAttempt.email == payload.email if payload.email else OtpAttempt.mobile_no == payload.mobile_no,
    )
    recent = (await session.execute(recent_stmt)).scalars().all()
    if len(recent) >= settings.otp_rate_limit_per_hour:
        raise RateLimitError("OTP request limit exceeded; try again later")

    code = generate_otp()
    if settings.environment != "production":
        # In dev / staging, always surface the OTP in logs so testers can
        # complete the flow without provisioning email / WhatsApp providers.
        log.warning(
            "dev_otp_generated",
            channel=payload.channel,
            email=payload.email,
            mobile_no=payload.mobile_no,
            code=code,
        )
    salt = secrets.token_hex(16)
    attempt = OtpAttempt(
        mobile_no=payload.mobile_no,
        email=payload.email,
        channel=payload.channel,
        otp_hash=f"{salt}${hash_otp(code, salt)}",
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.otp_ttl_seconds),
        created_at=datetime.now(UTC),
        requester_ip=request.client.host if request.client else None,
    )
    session.add(attempt)
    await session.flush()

    delivered = False
    if payload.channel == "email" and payload.email:
        delivered = await send_otp_email(payload.email, code)
    elif payload.channel == "whatsapp" and payload.mobile_no and payload.isd_code:
        delivered = await send_otp_whatsapp(payload.isd_code, payload.mobile_no, code)

    attempt.delivery_status = "sent" if delivered else "failed"
    await session.commit()

    return OtpRequestResponse(
        delivery_id=str(attempt.id),
        expires_in_seconds=settings.otp_ttl_seconds,
        channel=payload.channel,
    )


@router.post("/otp/verify", response_model=TokenPair)
async def verify_otp(
    payload: OtpVerify, session: AsyncSession = Depends(get_session)
) -> TokenPair:
    now = datetime.now(UTC)
    stmt = (
        select(OtpAttempt)
        .where(
            OtpAttempt.consumed.is_(False),
            OtpAttempt.expires_at > now,
            OtpAttempt.channel == payload.channel,
            OtpAttempt.email == payload.email if payload.email else OtpAttempt.mobile_no == payload.mobile_no,
        )
        .order_by(OtpAttempt.created_at.desc())
        .limit(1)
    )
    attempt = (await session.execute(stmt)).scalar_one_or_none()
    if not attempt:
        raise UnauthorizedError("No active OTP found")
    if attempt.attempt_count >= 5:
        raise RateLimitError("Too many verification attempts")

    salt, expected = attempt.otp_hash.split("$", 1)
    if hash_otp(payload.code, salt) != expected:
        attempt.attempt_count += 1
        await session.commit()
        raise UnauthorizedError("Invalid OTP")

    attempt.consumed = True

    user_stmt = (
        select(User)
        .where(User.user_email == payload.email)
        if payload.email
        else select(User).where(User.mobile_no == payload.mobile_no)
    )
    user = (await session.execute(user_stmt)).scalar_one_or_none()
    if not user:
        user = User(
            user_id=_gen_user_id(),
            user_email=payload.email,
            isd_code="91" if payload.mobile_no else None,
            mobile_no=payload.mobile_no,
            user_type="Farmer",
        )
        session.add(user)
        await session.flush()

    access, refresh = issue_tokens(user.user_id)
    await session.commit()
    return TokenPair(access_token=access, refresh_token=refresh, user_id=user.user_id)


@router.post("/consent", status_code=204)
async def accept_consent(
    payload: ConsentAccept,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Record that the user accepted the AI / PII disclaimer.

    Persists both an audit row (``consent_log``) and the latest version
    on the user record (``users.consent_version``). DPDP Act 2023
    expects auditable consent — the consent_log keeps every acceptance,
    while ``consent_version`` makes "is the current version accepted?"
    a constant-time check.
    """
    session.add(
        ConsentLog(
            user_id=current_user.user_id,
            consent_version=payload.consent_version,
            accepted_at=datetime.now(UTC),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:300] or None,
        )
    )
    current_user.consent_version = payload.consent_version
    await session.commit()
