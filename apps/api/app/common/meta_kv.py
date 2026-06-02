"""Tiny key/value table for operational state (last-export-at, etc.).

See migration 0010 for the schema. The DSL here is intentionally
minimal — get / set / cas — so callers don't reach for it as a
configuration mechanism (env vars are still right for that).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get(session: AsyncSession, key: str) -> str | None:
    """Return the value for ``key`` or ``None`` if it's not set."""
    result = await session.execute(
        text("SELECT value FROM meta_kv WHERE key = :k"), {"k": key}
    )
    row = result.scalar_one_or_none()
    return row if row is not None else None


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    """Upsert. Commits internally so callers can fire-and-forget."""
    await session.execute(
        text(
            "INSERT INTO meta_kv (key, value, updated_at) "
            "VALUES (:k, :v, :ts) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
            "updated_at = EXCLUDED.updated_at"
        ),
        {"k": key, "v": value, "ts": datetime.now(UTC)},
    )
    await session.commit()


async def get_datetime(session: AsyncSession, key: str) -> datetime | None:
    """Parse an ISO-8601 datetime, returning ``None`` for missing / unparseable."""
    raw = await get(session, key)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


async def set_datetime(session: AsyncSession, key: str, dt: datetime) -> None:
    """Persist a datetime as ISO-8601 string."""
    await set_value(session, key, dt.isoformat())
