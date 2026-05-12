"""Presign tests — happy path + mime-type rejection."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.uploads.models import ImageUpload


async def test_presign_happy_path(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """A valid presign request returns a URL + persists an ImageUpload row."""
    user_id, headers = authed_user
    r = await client.post(
        "/uploads/presign",
        headers=headers,
        json={
            "image_name": "leaf.jpg",
            "mime_type": "image/jpeg",
            "size_bytes": 50000,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["upload_url"].startswith("https://stub.test/PUT")
    assert body["expires_in_seconds"] > 0
    assert body["storage_location"].startswith(f"uploads/{user_id}/")

    img = await db_session.get(ImageUpload, uuid.UUID(body["image_id"]))
    assert img is not None
    assert img.user_id == user_id
    assert img.image_file_type == "jpeg"
    assert img.mime_type == "image/jpeg"
    assert img.size_bytes == 50000
    assert img.moderation_status == "pending"


async def test_presign_rejects_unsupported_mime(
    client: AsyncClient, authed_user: tuple[str, dict[str, str]]
) -> None:
    """PDF / non-image mime types are 409 — keep the diagnostic pipeline clean."""
    _, headers = authed_user
    r = await client.post(
        "/uploads/presign",
        headers=headers,
        json={
            "image_name": "doc.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1000,
        },
    )
    assert r.status_code == 409
    assert "Unsupported mime type" in r.json()["detail"]


async def test_presign_requires_token(client: AsyncClient) -> None:
    """No bearer token -> 401, never 200 or 500."""
    r = await client.post(
        "/uploads/presign",
        json={
            "image_name": "leaf.jpg",
            "mime_type": "image/jpeg",
            "size_bytes": 50000,
        },
    )
    assert r.status_code == 401
