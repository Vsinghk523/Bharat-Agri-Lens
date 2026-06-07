from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_admin, get_current_user
from app.common.errors import NotFoundError, UnauthorizedError
from app.db import get_session
from app.reminders.models import OutbreakAlert
from app.users.models import User
from app.users.schemas import PreferencesUpdate, UserPreferences, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await session.commit()
    await session.refresh(current_user)
    return current_user


@router.patch("/me/preferences", response_model=UserPreferences)
async def update_my_preferences(
    payload: PreferencesUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> UserPreferences:
    """Partial update of the user's notification + privacy toggles.

    Returns the *merged* preferences object (defaults filled in for
    any keys the user hasn't set yet) so the client never has to
    apply defaults locally.
    """
    # Start from the canonical "what we know about today" view.
    current = UserPreferences.from_raw(current_user.preferences).model_dump()
    # Layer the incoming partial update on top.
    update = payload.model_dump(exclude_unset=True)
    current.update(update)
    current_user.preferences = current
    await session.commit()
    await session.refresh(current_user)
    return UserPreferences.from_raw(current_user.preferences)


class OutbreakSummary(BaseModel):
    """One row per active outbreak relevant to this user. The Home
    page's 'In your area' panel reads from here."""

    pincode: str
    infection_type: str
    report_count: int
    notified_at: datetime


class OutbreakSummaryResponse(BaseModel):
    items: list[OutbreakSummary]


@router.get("/me/outbreak-alerts", response_model=OutbreakSummaryResponse)
async def my_outbreak_alerts(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OutbreakSummaryResponse:
    """Recent outbreak alerts targeting this user's pincode.

    Returns rows from ``outbreak_alerts`` recorded in the last 14
    days. The Home page panel renders the freshest entry; the
    longer history is available for clients that want to show a
    list view.

    Empty list when:
    - User hasn't set a pincode yet (the cron skips no-pincode users)
    - No outbreak in their pincode crossed the threshold recently
    - All recent outbreaks have been dismissed (future feature; v0
      always returns the raw rows)
    """
    cutoff = datetime.now(UTC) - timedelta(days=14)
    rows = (
        await session.execute(
            select(OutbreakAlert)
            .where(
                OutbreakAlert.user_id == current_user.user_id,
                OutbreakAlert.notified_at >= cutoff,
            )
            .order_by(OutbreakAlert.notified_at.desc())
            .limit(5)
        )
    ).scalars().all()
    return OutbreakSummaryResponse(
        items=[
            OutbreakSummary(
                pincode=r.pincode,
                infection_type=r.infection_type,
                report_count=r.report_count,
                notified_at=r.notified_at,
            )
            for r in rows
        ]
    )


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    # Self-service only. Admin lookups should go through a separate guarded path.
    if user_id != current_user.user_id:
        raise UnauthorizedError("Not allowed")
    user = await session.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise NotFoundError("User")
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> User:
    if user_id != current_user.user_id:
        raise UnauthorizedError("Not allowed")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await session.commit()
    await session.refresh(current_user)
    return current_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    if user_id != current_user.user_id:
        raise UnauthorizedError("Not allowed")
    current_user.status = "Inactive"
    current_user.deleted_at = datetime.now(UTC)
    await session.commit()


@router.delete("/{user_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
async def hard_delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Hard delete — DPDP Act 2023 right to erasure.

    A user may purge their own account; an admin may purge any account.
    Self-purge keeps the right-to-erasure path one click away in the
    UI; the admin path lets staff handle deletion requests that come
    through support channels.
    """
    target_user: User
    if user_id == current_user.user_id:
        target_user = current_user
    elif current_user.role == "admin":
        loaded = await session.get(User, user_id)
        if not loaded:
            raise NotFoundError("User")
        target_user = loaded
    else:
        raise UnauthorizedError("Not allowed")
    await session.delete(target_user)
    await session.commit()
