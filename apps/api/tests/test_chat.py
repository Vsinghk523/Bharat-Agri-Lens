"""Chat exchange tests — round-trip through (mocked) inference + Bhashini."""

from __future__ import annotations

from unittest.mock import AsyncMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import ChatMessage, ChatSession


async def test_chat_exchange_creates_both_messages(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    """POST /chat/messages persists user + assistant bubbles and returns
    both in a single ChatExchange payload."""
    monkeypatch.setattr(
        "app.chat.router._call_chat_inference",
        AsyncMock(return_value="For pest issues, spray neem oil weekly."),
    )

    _, headers = authed_user
    r = await client.post(
        "/chat/messages",
        headers=headers,
        json={"language": "en-IN", "content_text": "I see pests on my crop."},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["session_id"]
    assert body["user_message"]["content_text"] == "I see pests on my crop."
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"] is not None
    assert (
        body["assistant_message"]["content_text"]
        == "For pest issues, spray neem oil weekly."
    )
    assert body["assistant_message"]["role"] == "assistant"
    assert body["error"] is None

    # Both messages landed in the DB on the same session.
    rows = (
        await db_session.execute(
            select(ChatMessage).order_by(ChatMessage.add_date.asc())
        )
    ).scalars().all()
    assert len(rows) == 2
    assert {r.role for r in rows} == {"user", "assistant"}


async def test_chat_exchange_autocreates_session(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    """When session_id is omitted, the server creates a fresh session."""
    monkeypatch.setattr(
        "app.chat.router._call_chat_inference",
        AsyncMock(return_value="Hello."),
    )

    _, headers = authed_user

    # Confirm no sessions exist for this user yet.
    pre = (await db_session.execute(select(ChatSession))).scalars().all()
    assert pre == []

    r = await client.post(
        "/chat/messages",
        headers=headers,
        json={"content_text": "Hi"},  # no session_id
    )
    assert r.status_code == 201, r.text
    body = r.json()
    new_id = body["session_id"]
    assert new_id

    post = (await db_session.execute(select(ChatSession))).scalars().all()
    assert len(post) == 1
    assert str(post[0].session_id) == new_id


async def test_chat_exchange_round_trips_through_hindi(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    monkeypatch,
) -> None:
    """For a hi-IN user the inference call receives English (the mock
    translator prefixed the input) and the reply comes back wrapped in
    the same prefix shape for the user."""
    capture: dict[str, str] = {}

    async def fake_inference(message: str) -> str:
        capture["seen"] = message
        return "Spray neem oil weekly."

    monkeypatch.setattr("app.chat.router._call_chat_inference", fake_inference)

    _, headers = authed_user
    r = await client.post(
        "/chat/messages",
        headers=headers,
        json={"language": "hi-IN", "content_text": "मेरी फसल में कीट हैं"},
    )
    assert r.status_code == 201, r.text
    body = r.json()

    # The inference service was handed the mock-English version of the
    # user input.
    assert capture["seen"].startswith("en «")
    # The assistant reply was translated back into the mock-Hindi shape.
    assert body["assistant_message"]["content_text"].startswith("hi «")
    assert "Spray neem oil weekly." in body["assistant_message"]["content_text"]


async def test_chat_exchange_handles_inference_offline(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    """If the inference service returns None, the user bubble still
    persists and the response carries a structured error code instead
    of a 5xx."""
    monkeypatch.setattr(
        "app.chat.router._call_chat_inference",
        AsyncMock(return_value=None),
    )

    _, headers = authed_user
    r = await client.post(
        "/chat/messages",
        headers=headers,
        json={"content_text": "Anyone home?"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["assistant_message"] is None
    assert body["error"] == "inference_unavailable"

    # The user message persisted; the assistant message did not.
    rows = (await db_session.execute(select(ChatMessage))).scalars().all()
    assert len(rows) == 1
    assert rows[0].role == "user"
