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


async def test_download_url_returns_thumbnail_when_approved(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """Once moderation has set ``thumbnail_location``, the response
    includes a presigned URL for it alongside the original."""
    user_id, headers = authed_user
    img = ImageUpload(
        image_id=uuid.uuid4(),
        user_id=user_id,
        image_name="x.png",
        image_file_type="png",
        storage_location=f"uploads/{user_id}/x.png",
        mime_type="image/png",
        moderation_status="approved",
        thumbnail_location=f"uploads/{user_id}/x.png.thumb.jpg",
    )
    db_session.add(img)
    await db_session.commit()

    r = await client.get(f"/uploads/{img.image_id}/url", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://stub.test/GET")
    assert body["thumbnail_url"] is not None
    assert body["thumbnail_url"].startswith("https://stub.test/GET")
    assert body["expires_in_seconds"] > 0


async def test_download_url_thumbnail_null_when_pending(
    client: AsyncClient,
    authed_user: tuple[str, dict[str, str]],
    db_session: AsyncSession,
) -> None:
    """Before moderation runs, ``thumbnail_url`` is null. The original
    URL is still returned so the client has *something* to display."""
    user_id, headers = authed_user
    img = ImageUpload(
        image_id=uuid.uuid4(),
        user_id=user_id,
        image_name="x.png",
        image_file_type="png",
        storage_location=f"uploads/{user_id}/x.png",
        mime_type="image/png",
        moderation_status="pending",
    )
    db_session.add(img)
    await db_session.commit()

    r = await client.get(f"/uploads/{img.image_id}/url", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://stub.test/GET")
    assert body["thumbnail_url"] is None
