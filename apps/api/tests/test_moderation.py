"""Image moderation worker tests."""

from __future__ import annotations

import io
import uuid
from unittest.mock import MagicMock

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.uploads.models import ImageUpload
from app.users.models import User


def _png_bytes(color: str = "green", size: tuple[int, int] = (64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _make_upload(user_id: str) -> ImageUpload:
    return ImageUpload(
        image_id=uuid.uuid4(),
        user_id=user_id,
        image_name="x.png",
        image_file_type="png",
        storage_location=f"uploads/{user_id}/x.png",
        mime_type="image/png",
        moderation_status="pending",
    )


def _stub_s3(*, body: bytes) -> MagicMock:
    client = MagicMock()
    client.get_object.return_value = {"Body": MagicMock(read=lambda: body)}
    client.put_object.return_value = {}
    return client


async def _seed_user(session: AsyncSession, user_id: str) -> User:
    user = User(
        user_id=user_id,
        user_email=f"{user_id.lower()}@test.example.com",
        user_type="Farmer",
    )
    session.add(user)
    await session.commit()
    return user


async def test_moderation_approves_valid_image(
    db_session: AsyncSession, monkeypatch
) -> None:
    """A real PNG flows through to ``approved`` + thumbnail written."""
    from app.jobs import moderation

    await _seed_user(db_session, "MOD0000001")

    img_bytes = _png_bytes()
    img = _make_upload("MOD0000001")
    db_session.add(img)
    await db_session.commit()

    client = _stub_s3(body=img_bytes)
    monkeypatch.setattr(moderation, "get_s3_client", lambda: client)

    result = await moderation.process_one(db_session, img)
    await db_session.commit()

    assert result == "approved"
    assert img.moderation_status == "approved"
    assert img.size_bytes == len(img_bytes)
    assert img.content_hash and len(img.content_hash) == 64
    assert img.thumbnail_location and img.thumbnail_location.endswith(".thumb.jpg")

    client.put_object.assert_called_once()
    put_kwargs = client.put_object.call_args.kwargs
    assert put_kwargs["ContentType"] == "image/jpeg"
    assert put_kwargs["Key"].endswith(".thumb.jpg")
    # The thumbnail must itself be a parseable JPEG.
    thumb_bytes = put_kwargs["Body"]
    Image.open(io.BytesIO(thumb_bytes)).verify()


async def test_moderation_rejects_non_image(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Random bytes from object storage flip the row to ``rejected``
    and we never attempt a thumbnail upload."""
    from app.jobs import moderation

    await _seed_user(db_session, "MOD0000002")

    img = _make_upload("MOD0000002")
    db_session.add(img)
    await db_session.commit()

    client = _stub_s3(body=b"this is definitely not an image")
    monkeypatch.setattr(moderation, "get_s3_client", lambda: client)

    result = await moderation.process_one(db_session, img)
    await db_session.commit()

    assert result == "rejected"
    assert img.moderation_status == "rejected"
    assert img.thumbnail_location is None
    client.put_object.assert_not_called()


async def test_moderation_rejects_oversize(
    db_session: AsyncSession, monkeypatch
) -> None:
    """Bytes larger than ``MODERATION_MAX_IMAGE_BYTES`` are rejected
    before Pillow gets anywhere near them."""
    from app.config import get_settings
    from app.jobs import moderation

    await _seed_user(db_session, "MOD0000003")

    img = _make_upload("MOD0000003")
    db_session.add(img)
    await db_session.commit()

    limit = get_settings().moderation_max_image_bytes
    fake_body = b"\x00" * (limit + 1)
    client = _stub_s3(body=fake_body)
    monkeypatch.setattr(moderation, "get_s3_client", lambda: client)

    result = await moderation.process_one(db_session, img)
    await db_session.commit()

    assert result == "rejected"
    assert img.moderation_status == "rejected"
    assert img.size_bytes == limit + 1
    client.put_object.assert_not_called()
