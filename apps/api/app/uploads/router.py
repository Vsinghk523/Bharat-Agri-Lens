import uuid
from datetime import UTC, datetime

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.common.s3 import (
    generate_get_url,
    generate_put_url,
    object_key_for_upload,
)
from app.logging import get_logger
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
log = get_logger(__name__)

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_STORAGE_UNAVAILABLE = (
    "Object storage is not configured on this deployment. "
    "Set S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, "
    "S3_BUCKET, and S3_REGION on the api service."
)


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
    try:
        upload_url = generate_put_url(
            key=key,
            mime_type=payload.mime_type,
            expires=settings.s3_presign_ttl_seconds,
        )
    except (BotoCoreError, ClientError) as exc:
        # Most commonly NoCredentialsError when S3 env vars aren't set on
        # the deployment. Returning a structured 503 lets the browser show
        # a real error instead of a CORS-stripped "Failed to fetch".
        log.warning("presign_failed", error=str(exc), key=key)
        raise ServiceUnavailableError(_STORAGE_UNAVAILABLE) from exc

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
    """Presigned GET URLs for the original image and its thumbnail.

    ``thumbnail_url`` is None until the moderation worker has produced
    the thumbnail; clients that fetch the URL right after upload should
    fall back to ``url`` and re-fetch a moment later for the smaller
    preview asset.
    """
    obj = await session.get(ImageUpload, image_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("ImageUpload")
    try:
        url = generate_get_url(obj.storage_location, settings.s3_presign_ttl_seconds)
        thumb_url = (
            generate_get_url(obj.thumbnail_location, settings.s3_presign_ttl_seconds)
            if obj.thumbnail_location
            else None
        )
    except (BotoCoreError, ClientError) as exc:
        log.warning("download_url_failed", error=str(exc), image_id=str(image_id))
        raise ServiceUnavailableError(_STORAGE_UNAVAILABLE) from exc
    return DownloadUrlResponse(
        url=url,
        thumbnail_url=thumb_url,
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
