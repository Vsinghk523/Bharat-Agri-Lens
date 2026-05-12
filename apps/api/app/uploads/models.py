import uuid

from sqlalchemy import BigInteger, CHAR, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import AuditMixin, Base


class ImageUpload(AuditMixin, Base):
    __tablename__ = "image_uploads"

    image_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(10), ForeignKey("users.user_id"), index=True)
    image_name: Mapped[str] = mapped_column(String(50))
    image_file_type: Mapped[str] = mapped_column(String(10))
    storage_location: Mapped[str] = mapped_column(String(200))

    content_hash: Mapped[str | None] = mapped_column(CHAR(64), index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(50))
    exif_captured_at: Mapped[str | None] = mapped_column(String(40))
    exif_lat: Mapped[str | None] = mapped_column(String(30))
    exif_lng: Mapped[str | None] = mapped_column(String(30))
    moderation_status: Mapped[str] = mapped_column(String(20), default="pending")
    thumbnail_location: Mapped[str | None] = mapped_column(String(200))
