import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.errors import NotFoundError
from app.config import get_settings
from app.db import get_session
from app.uploads.models import ImageUpload
from app.uploads.schemas import ImageUploadRead, PresignRequest, PresignResponse
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
        from app.common.errors import ConflictError

        raise ConflictError(f"Unsupported mime type: {payload.mime_type}")

    image_id = uuid.uuid4()
    key = f"uploads/{image_id}/{payload.image_name}"
    # TODO: integrate boto3 generate_presigned_url. Stub for scaffold.
    upload_url = f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/{key}?stub=1"

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
