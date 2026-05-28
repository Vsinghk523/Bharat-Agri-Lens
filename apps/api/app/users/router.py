from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_admin, get_current_user
from app.common.errors import NotFoundError, UnauthorizedError
from app.db import get_session
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
