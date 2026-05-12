import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PresignRequest(BaseModel):
    image_name: str = Field(..., min_length=1, max_length=50)
    mime_type: str
    size_bytes: int = Field(..., gt=0, le=10 * 1024 * 1024)


class PresignResponse(BaseModel):
    image_id: uuid.UUID
    upload_url: str
    storage_location: str
    expires_in_seconds: int


class DownloadUrlResponse(BaseModel):
    url: str
    expires_in_seconds: int


class ImageUploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    image_id: uuid.UUID
    user_id: str
    image_name: str
    image_file_type: str
    storage_location: str
    size_bytes: int | None
    mime_type: str | None
    moderation_status: str
    status: str
    add_date: datetime
