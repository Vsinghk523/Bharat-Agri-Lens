"""Authentication dependencies for FastAPI routers."""

from __future__ import annotations

from fastapi import Depends, Header
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import UnauthorizedError
from app.config import get_settings
from app.db import get_session
from app.users.models import User

settings = get_settings()


async def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Decode the Bearer access token and load the matching user.

    Raises 401 if:
      - no header / wrong scheme
      - token is invalid, expired, or not an access token
      - user does not exist or is soft-deleted
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise UnauthorizedError(f"Invalid token: {exc}") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Wrong token type")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError("Token missing subject")

    user = await session.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise UnauthorizedError("User not found")
    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Bearer token + role=='admin' guard for /admin/* and DPDP purge.

    Composes on top of ``get_current_user`` so misuse (no token) still
    surfaces as 401 rather than 403 — the caller hasn't even
    identified themselves yet at that point.
    """
    if current_user.role != "admin":
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user
