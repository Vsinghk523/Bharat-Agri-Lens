from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import NotFoundError
from app.db import get_session
from app.users.models import User
from app.users.schemas import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: str, session: AsyncSession = Depends(get_session)) -> User:
    user = await session.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise NotFoundError("User")
    return user


@router.get("", response_model=list[UserRead])
async def list_users(
    limit: int = 50, offset: int = 0, session: AsyncSession = Depends(get_session)
) -> list[User]:
    stmt = (
        select(User)
        .where(User.deleted_at.is_(None))
        .order_by(User.add_date.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: str, payload: UserUpdate, session: AsyncSession = Depends(get_session)
) -> User:
    user = await session.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise NotFoundError("User")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_user(user_id: str, session: AsyncSession = Depends(get_session)) -> None:
    user = await session.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise NotFoundError("User")
    user.status = "Inactive"
    from datetime import UTC, datetime

    user.deleted_at = datetime.now(UTC)
    await session.commit()


@router.delete("/{user_id}/purge", status_code=status.HTTP_204_NO_CONTENT)
async def hard_delete_user(user_id: str, session: AsyncSession = Depends(get_session)) -> None:
    """Hard delete — DPDP Act 2023 right to erasure. Admin only (TODO: guard)."""
    user = await session.get(User, user_id)
    if not user:
        raise NotFoundError("User")
    await session.delete(user)
    await session.commit()
