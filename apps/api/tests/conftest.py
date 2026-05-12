"""Pytest fixtures for the BharatAgriLens API.

Strategy
--------
- Set DATABASE_URL + ENVIRONMENT in os.environ BEFORE any ``app.*`` import,
  so ``Settings`` is constructed against the test database from the very
  first ``get_settings()`` call.
- Session-scoped: drop and recreate the test database, then build all
  tables via ``Base.metadata.create_all`` (no Alembic — much faster, and
  the migrations are exercised separately in CI).
- Function-scoped: open a connection, begin a transaction, wrap it in a
  savepoint, run the test, roll everything back. Router-level commits
  end up as savepoint-commits and never persist.
- The HTTP client uses ``httpx.ASGITransport`` so no port is bound and
  the FastAPI lifespan runs naturally (with boto3 / SMTP / WhatsApp
  patched to no-ops so tests don't need MinIO / Resend / Meta to be up).
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# ---- Set env BEFORE any app.* import; pydantic-settings reads env on construction ----
os.environ["ENVIRONMENT"] = "test"
_DEV_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/bharat_agri_lens",
)
_TEST_DB = "bharat_agri_lens_test"
_BASE_URL = _DEV_URL.rsplit("/", 1)[0]
os.environ["DATABASE_URL"] = f"{_BASE_URL}/{_TEST_DB}"
# Provide a deterministic JWT secret so issue_tokens + decode line up.
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-prod-" + "x" * 40)
os.environ.setdefault("CPA_FERNET_KEY", "rRfaiU8DKZpgrfHVtL1Yc7iSitZuLymvxJZE1k60K0g=")

# Safe now to import the app.
from app.common.base import Base  # noqa: E402

# Import every model module so all tables are registered on Base.metadata.
from app.auth import models as _m_auth  # noqa: F401, E402
from app.chat import models as _m_chat  # noqa: F401, E402
from app.diagnostics import models as _m_diag  # noqa: F401, E402
from app.uploads import models as _m_upload  # noqa: F401, E402
from app.users import models as _m_user  # noqa: F401, E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _provision_test_db() -> AsyncIterator[None]:
    """Drop + recreate the test database once per session."""
    admin_engine = create_async_engine(
        f"{_BASE_URL}/postgres",
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    async with admin_engine.connect() as conn:
        # FORCE breaks idle client sessions so the drop succeeds.
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_DB}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{_TEST_DB}"'))
    await admin_engine.dispose()
    yield


@pytest_asyncio.fixture(scope="session")
async def test_engine(_provision_test_db) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield a per-test session. Truncate every table beforehand so
    each test starts on a known-empty database.

    Earlier iterations used a SAVEPOINT-per-test recipe to avoid I/O
    between runs; in practice that fought the async commits that the
    FastAPI dependency-override path performs from inside the same
    session. TRUNCATE CASCADE is microseconds per test and keeps the
    fixture readable.
    """
    table_names = ", ".join(
        f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
    )
    async with test_engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
        )

    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """ASGI HTTP client whose API requests reuse the per-test session.

    External integrations are stubbed for the duration of the client:
    - ``ensure_bucket`` / ``ensure_cors`` short-circuit (no MinIO needed).
    - ``generate_put_url`` / ``generate_get_url`` return fixed stub URLs.
    - ``send_otp_email`` / ``send_otp_whatsapp`` return True without
      hitting Resend or Meta.
    """
    from app.db import get_session

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    with (
        # Patch the bindings *where they are imported and called*,
        # not where they are originally defined.
        patch("app.main.ensure_bucket", return_value=True),
        patch("app.main.ensure_cors", return_value=True),
        patch(
            "app.uploads.router.generate_put_url",
            return_value="https://stub.test/PUT?x=1",
        ),
        patch(
            "app.uploads.router.generate_get_url",
            return_value="https://stub.test/GET?x=1",
        ),
        patch(
            "app.auth.router.send_otp_email",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.auth.router.send_otp_whatsapp",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        from app.main import app

        app.dependency_overrides[get_session] = _override_get_session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.pop(get_session, None)


async def _make_user(
    db_session: AsyncSession, role: str = "user"
) -> tuple[str, dict[str, str]]:
    """Insert a user with the given role and mint an access token."""
    from app.auth.service import issue_tokens
    from app.users.models import User

    user = User(
        user_id=secrets.token_hex(5).upper(),
        user_email=f"u-{secrets.token_hex(4)}@test.example.com",
        user_type="Farmer",
        preferred_language="en-IN",
        role=role,
    )
    db_session.add(user)
    await db_session.commit()

    access, _ = issue_tokens(user.user_id)
    return user.user_id, {"Authorization": f"Bearer {access}"}


@pytest_asyncio.fixture
async def authed_user(db_session: AsyncSession) -> tuple[str, dict[str, str]]:
    """A standard end-user with role='user'."""
    return await _make_user(db_session, role="user")


@pytest_asyncio.fixture
async def authed_admin(db_session: AsyncSession) -> tuple[str, dict[str, str]]:
    """A user with role='admin' for /admin/* and DPDP-purge tests."""
    return await _make_user(db_session, role="admin")
