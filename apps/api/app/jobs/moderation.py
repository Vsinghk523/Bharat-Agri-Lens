"""Image moderation + thumbnail worker.

Poll Postgres every ``MODERATION_POLL_INTERVAL_SECONDS`` for rows in
``image_uploads`` with ``moderation_status='pending'``. For each row:

1. Download the original from object storage.
2. Reject if the byte count exceeds ``MODERATION_MAX_IMAGE_BYTES`` —
   the presign API already enforces this, but the worker is the
   source of truth (a client could lie in the presign request).
3. Verify with Pillow that the payload is actually an image; reject
   on parse error or disallowed format.
4. Compute the SHA-256 ``content_hash`` from the actual bytes.
5. Render a ``THUMBNAIL_MAX_DIM``-bounded JPEG thumbnail and upload it
   alongside the original at ``<storage_location>.thumb.jpg``.
6. Flip ``moderation_status`` to ``approved``, write
   ``thumbnail_location``, the real ``size_bytes`` and ``content_hash``.

Concurrency-safe via ``SELECT … FOR UPDATE SKIP LOCKED``: many API
replicas can run this worker simultaneously; each batch goes to one
worker, untouched rows go to the next.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.s3 import get_s3_client
from app.config import get_settings
from app.db import AsyncSessionLocal
from app.logging import get_logger
from app.uploads.models import ImageUpload

log = get_logger(__name__)

# Pillow format names (uppercased) the worker accepts.
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def _process_image_sync(image_bytes: bytes, max_dim: int, jpeg_quality: int) -> tuple[
    str, bytes, dict[str, Any]
]:
    """CPU-bound: validate the image, compute hash, render a JPEG thumbnail.

    Run via ``asyncio.to_thread`` so the event loop keeps moving while
    Pillow decodes / resizes a multi-megapixel image.
    """
    sha = hashlib.sha256(image_bytes).hexdigest()

    # verify() consumes the stream and only inspects metadata; we still
    # need a fresh handle for the resize.
    try:
        probe = Image.open(io.BytesIO(image_bytes))
        probe.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"image could not be parsed: {exc}") from exc

    if probe.format not in ALLOWED_FORMATS:
        raise ValueError(f"image format {probe.format!r} not allowed")

    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size
    img.thumbnail((max_dim, max_dim))
    thumb_buf = io.BytesIO()
    # JPEG can't carry alpha — flatten on a white background so PNGs/WEBPs
    # don't lose information silently to a black background.
    rgb = img.convert("RGB") if img.mode != "RGB" else img
    rgb.save(thumb_buf, format="JPEG", quality=jpeg_quality, optimize=True)
    return sha, thumb_buf.getvalue(), {
        "format": probe.format,
        "width": width,
        "height": height,
    }


async def process_one(session: AsyncSession, upload: ImageUpload) -> str:
    """Run the full moderation pipeline against a single ImageUpload row.

    Returns the final ``moderation_status`` value. The caller owns
    transaction lifecycle and may want to commit / rollback batches.
    """
    settings = get_settings()
    client = get_s3_client()

    try:
        obj = await asyncio.to_thread(
            client.get_object, Bucket=settings.s3_bucket, Key=upload.storage_location
        )
        body_bytes: bytes = obj["Body"].read()
    except Exception as exc:
        upload.moderation_status = "rejected"
        log.warning(
            "moderation_rejected",
            image_id=str(upload.image_id),
            reason="fetch_failed",
            error=str(exc),
        )
        return "rejected"

    actual_size = len(body_bytes)
    if actual_size > settings.moderation_max_image_bytes:
        upload.moderation_status = "rejected"
        upload.size_bytes = actual_size
        log.warning(
            "moderation_rejected",
            image_id=str(upload.image_id),
            reason="too_large",
            size=actual_size,
            limit=settings.moderation_max_image_bytes,
        )
        return "rejected"

    try:
        sha, thumb_bytes, meta = await asyncio.to_thread(
            _process_image_sync,
            body_bytes,
            settings.thumbnail_max_dim,
            settings.thumbnail_jpeg_quality,
        )
    except ValueError as exc:
        upload.moderation_status = "rejected"
        upload.size_bytes = actual_size
        log.warning(
            "moderation_rejected",
            image_id=str(upload.image_id),
            reason="parse_failed",
            error=str(exc),
        )
        return "rejected"

    thumb_key = f"{upload.storage_location}.thumb.jpg"
    try:
        await asyncio.to_thread(
            client.put_object,
            Bucket=settings.s3_bucket,
            Key=thumb_key,
            Body=thumb_bytes,
            ContentType="image/jpeg",
        )
    except Exception as exc:
        upload.moderation_status = "rejected"
        upload.size_bytes = actual_size
        upload.content_hash = sha
        log.warning(
            "moderation_rejected",
            image_id=str(upload.image_id),
            reason="thumbnail_upload_failed",
            error=str(exc),
        )
        return "rejected"

    upload.content_hash = sha
    upload.size_bytes = actual_size
    upload.thumbnail_location = thumb_key
    upload.moderation_status = "approved"
    log.info(
        "moderation_approved",
        image_id=str(upload.image_id),
        size=actual_size,
        sha=sha[:12],
        format=meta["format"],
        dims=f"{meta['width']}x{meta['height']}",
    )
    return "approved"


async def _process_batch() -> int:
    """Lock + process one batch of pending uploads. Returns the count
    of rows touched in this call."""
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ImageUpload)
            .where(
                ImageUpload.moderation_status == "pending",
                ImageUpload.deleted_at.is_(None),
            )
            .order_by(ImageUpload.add_date.asc())
            .limit(settings.moderation_batch_size)
            .with_for_update(skip_locked=True)
        )
        async with session.begin():
            rows = list((await session.execute(stmt)).scalars().all())
            for row in rows:
                try:
                    await process_one(session, row)
                except Exception:
                    # Defensive — process_one already handles its own
                    # error paths, but if it ever bubbles up we mark the
                    # row rejected so the loop doesn't burn the CPU
                    # retrying the same bad input forever.
                    log.exception(
                        "moderation_unexpected_failure",
                        image_id=str(row.image_id),
                    )
                    row.moderation_status = "rejected"
        return len(rows)


async def moderation_loop(stop_event: asyncio.Event) -> None:
    """Run forever (until stop_event is set) processing pending uploads."""
    settings = get_settings()
    log.info(
        "moderation_loop_started",
        interval=settings.moderation_poll_interval_seconds,
        batch=settings.moderation_batch_size,
    )
    while not stop_event.is_set():
        try:
            await _process_batch()
        except Exception:
            log.exception("moderation_loop_iteration_failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.moderation_poll_interval_seconds
            )
        except asyncio.TimeoutError:
            pass
    log.info("moderation_loop_stopped")
