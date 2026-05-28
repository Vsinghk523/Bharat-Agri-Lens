"""HTTP endpoints for FCM token registration."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db import get_session
from app.push.models import FcmToken
from app.push.schemas import TokenRegister, TokenRegisterResponse
from app.users.models import User

router = APIRouter(prefix="/push", tags=["push"])


@router.post(
    "/register-token",
    response_model=TokenRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_token(
    payload: TokenRegister,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TokenRegisterResponse:
    """Idempotently register an FCM token for the current user.

    The Capacitor app calls this on every cold start (FCM may have
    rotated the token), so the upsert behavior matters: if the row
    exists we just refresh ``last_seen_at`` and reset ``failure_count``;
    if it doesn't, we insert.

    Why not require uniqueness server-side via ``ON CONFLICT``? We do —
    the table's PK on (user_id, token) is the conflict guard. We use
    the manual select-then-upsert here rather than ``insert().on_conflict``
    because we also want to flip ``status`` back to Active and zero
    ``failure_count`` on the conflict path (a previously-stale token
    can come back to life if the user reinstalls).
    """
    existing = (
        await session.execute(
            select(FcmToken).where(
                FcmToken.user_id == current_user.user_id,
                FcmToken.token == payload.token,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing:
        existing.last_seen_at = now
        existing.failure_count = 0
        existing.status = "Active"
        # Platform may legitimately change (user moved from web to
        # Android with the same Google account); record the latest.
        existing.platform = payload.platform
    else:
        session.add(
            FcmToken(
                user_id=current_user.user_id,
                token=payload.token,
                platform=payload.platform,
                registered_at=now,
                last_seen_at=now,
                failure_count=0,
                status="Active",
            )
        )
    await session.commit()
    return TokenRegisterResponse(ok=True)


@router.delete(
    "/register-token",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unregister_token(
    token: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Remove a specific FCM token for the current user.

    Called on sign-out from that device. We mark the row Stale rather
    than delete it so we can analyse re-registrations later. The
    cascading delete on user_id still nukes everything on account
    purge.
    """
    existing = (
        await session.execute(
            select(FcmToken).where(
                FcmToken.user_id == current_user.user_id,
                FcmToken.token == token,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.status = "Stale"
        await session.commit()
