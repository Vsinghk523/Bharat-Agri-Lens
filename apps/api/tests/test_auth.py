"""OTP flow + JWT guard tests."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import OtpAttempt


async def test_otp_request_persists_attempt(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Requesting an OTP creates an OtpAttempt row regardless of delivery."""
    r = await client.post(
        "/auth/otp/request",
        json={"channel": "email", "email": "fresh@test.example.com"},
    )
    assert r.status_code == 200, r.text

    stmt = select(OtpAttempt).where(OtpAttempt.email == "fresh@test.example.com")
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.channel == "email"
    assert row.consumed is False
    # Delivery was stubbed to succeed.
    assert row.delivery_status == "sent"


async def test_full_otp_login_returns_working_token(
    client: AsyncClient, monkeypatch
) -> None:
    """Happy path: request OTP, verify, then use the access token."""
    # Pin the OTP so the test doesn't need to read it from logs / DB.
    # The router imports generate_otp by name, so we patch the binding
    # in the router module — patching service.generate_otp wouldn't
    # change the already-resolved reference in router.py.
    monkeypatch.setattr("app.auth.router.generate_otp", lambda digits=6: "424242")

    r1 = await client.post(
        "/auth/otp/request",
        json={"channel": "email", "email": "fullflow@test.example.com"},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.post(
        "/auth/otp/verify",
        json={"channel": "email", "email": "fullflow@test.example.com", "code": "424242"},
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user_id"]

    me = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["user_email"] == "fullflow@test.example.com"


async def test_protected_endpoint_requires_token(client: AsyncClient) -> None:
    r = await client.get("/users/me")
    assert r.status_code == 401


async def test_protected_endpoint_rejects_garbage_token(client: AsyncClient) -> None:
    r = await client.get(
        "/users/me",
        headers={"Authorization": "Bearer not-a-real-token-at-all"},
    )
    assert r.status_code == 401


async def test_refresh_token_rejected_as_access(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """Refresh tokens carry type='refresh' and must NOT pass the access guard."""
    from app.auth.service import issue_tokens

    user_id, _ = authed_user
    _, refresh = issue_tokens(user_id)
    r = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert r.status_code == 401
