import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.errors import ConflictError, NotFoundError
from app.common.s3 import (
    generate_get_url,
    generate_put_url,
    object_key_for_upload,
)
from app.config import get_settings
from app.db import get_session
from app.uploads.models import ImageUpload
from app.uploads.schemas import (
    DownloadUrlResponse,
    ImageUploadRead,
    PresignRequest,
    PresignResponse,
)
from app.users.models import User

router = APIRouter(prefix="/uploads", tags=["uploads"])
settings = get_settings()

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post("/presign", response_model=PresignResponse)
async def presign_upload(
    payload: PresignRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PresignResponse:
    if payload.mime_type not in _ALLOWED_MIME:
        raise ConflictError(f"Unsupported mime type: {payload.mime_type}")

    image_id = uuid.uuid4()
    key = object_key_for_upload(current_user.user_id, str(image_id), payload.image_name)
    upload_url = generate_put_url(
        key=key,
        mime_type=payload.mime_type,
        expires=settings.s3_presign_ttl_seconds,
    )

    record = ImageUpload(
        image_id=image_id,
        user_id=current_user.user_id,
        image_name=payload.image_name,
        image_file_type=payload.mime_type.split("/")[-1],
        storage_location=key,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        moderation_status="pending",
    )
    session.add(record)
    await session.commit()

    return PresignResponse(
        image_id=image_id,
        upload_url=upload_url,
        storage_location=key,
        expires_in_seconds=settings.s3_presign_ttl_seconds,
    )


@router.get("/{image_id}/url", response_model=DownloadUrlResponse)
async def get_download_url(
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DownloadUrlResponse:
    """Presigned GET URL the client can use to display / download the image."""
    obj = await session.get(ImageUpload, image_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("ImageUpload")
    url = generate_get_url(obj.storage_location, settings.s3_presign_ttl_seconds)
    return DownloadUrlResponse(
        url=url,
        expires_in_seconds=settings.s3_presign_ttl_seconds,
    )


@router.get("/{image_id}", response_model=ImageUploadRead)
async def get_upload(
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ImageUpload:
    obj = await session.get(ImageUpload, image_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("ImageUpload")
    return obj


@router.get("", response_model=list[ImageUploadRead])
async def list_uploads(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ImageUpload]:
    stmt = (
        select(ImageUpload)
        .where(
            ImageUpload.deleted_at.is_(None),
            ImageUpload.user_id == current_user.user_id,
        )
        .order_by(ImageUpload.add_date.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_upload(
    image_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    obj = await session.get(ImageUpload, image_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("ImageUpload")
    obj.status = "Inactive"
    obj.deleted_at = datetime.now(UTC)
    await session.commit()
