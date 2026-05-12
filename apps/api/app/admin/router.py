"""Admin / data-ops endpoints.

The labelling queue is the entry point for the active-learning loop:
every diagnostic the user flagged ``incorrect`` or ``partial`` is a
candidate for human re-labelling. Reviewers pull this queue weekly,
hit the PATCH endpoint with their authoritative labels, and the
corrected rows feed back into ``services/training/`` on the next run.

Gating: the whole router lives behind ``get_current_admin`` — Bearer
token + ``users.role == 'admin'``. Non-admin tokens get 403 (not 404)
so an admin tool can tell "wrong role" from "missing endpoint"
without leaking the schema to anonymous traffic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    LabellingQueueItem,
    LabellingQueueResponse,
    ReviewerCorrection,
)
from app.auth.dependencies import get_current_admin
from app.common.errors import NotFoundError
from app.common.s3 import generate_get_url
from app.config import get_settings
from app.db import get_session
from app.diagnostics.models import PlantDiagnostic
from app.uploads.models import ImageUpload
from app.users.models import User

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()

_FLAGGED_VERDICTS = ("incorrect", "partial")


def _to_item(diag: PlantDiagnostic, image: ImageUpload | None) -> LabellingQueueItem:
    url: str | None = None
    if image is not None and image.storage_location:
        try:
            url = generate_get_url(image.storage_location, settings.s3_presign_ttl_seconds)
        except Exception:  # noqa: BLE001
            url = None
    return LabellingQueueItem(
        diagnostic_id=diag.diagnostic_id,
        image_id=diag.image_id,
        image_url=url,
        storage_location=image.storage_location if image else None,
        predicted_plant=diag.plant_classification,
        predicted_disease=diag.disease_name,
        predicted_infection_type=diag.infection_type,
        confidence_score=diag.confidence_score,
        user_feedback=diag.user_feedback or "",
        language_used=diag.language_used,
        add_date=diag.add_date,
        modify_date=diag.modify_date,
        correct_plant=diag.correct_plant,
        correct_disease=diag.correct_disease,
        correct_infection_type=diag.correct_infection_type,
        reviewed_by=diag.reviewed_by,
        reviewed_at=diag.reviewed_at,
    )


@router.get("/labelling-queue", response_model=LabellingQueueResponse)
async def labelling_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_admin),
) -> LabellingQueueResponse:
    """List diagnostics the user marked incorrect / partial.

    Each item carries the predicted labels (so reviewers can see what
    the model thought), a presigned URL to the original image, and any
    corrections an earlier reviewer has already applied — so a second
    pass over the queue can fix mistakes instead of duplicating work.
    """
    base_filter = [
        PlantDiagnostic.deleted_at.is_(None),
        PlantDiagnostic.user_feedback.in_(_FLAGGED_VERDICTS),
    ]

    total_stmt = select(func.count()).select_from(PlantDiagnostic).where(*base_filter)
    total = int((await session.execute(total_stmt)).scalar_one())

    rows_stmt = (
        select(PlantDiagnostic, ImageUpload)
        .outerjoin(ImageUpload, ImageUpload.image_id == PlantDiagnostic.image_id)
        .where(*base_filter)
        .order_by(PlantDiagnostic.modify_date.desc())
        .limit(limit)
        .offset(offset)
    )
    pairs = (await session.execute(rows_stmt)).all()
    items = [_to_item(diag, image) for diag, image in pairs]
    return LabellingQueueResponse(items=items, total=total, limit=limit, offset=offset)


@router.patch("/labelling-queue/{diagnostic_id}", response_model=LabellingQueueItem)
async def correct_diagnostic(
    diagnostic_id: uuid.UUID,
    payload: ReviewerCorrection,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(get_current_admin),
) -> LabellingQueueItem:
    """Apply an admin reviewer's authoritative re-label.

    The original ``plant_classification`` / ``disease_name`` /
    ``infection_type`` columns stay untouched (kept for audit and
    error-analysis) — the reviewer's correction goes into the
    parallel ``correct_*`` columns, and ``reviewed_by`` /
    ``reviewed_at`` are stamped server-side.

    Setting any field to ``null`` in the request body clears that
    correction; omitted fields keep their existing value (PATCH
    semantics).
    """
    diag = await session.get(PlantDiagnostic, diagnostic_id)
    if not diag or diag.deleted_at is not None:
        raise NotFoundError("Diagnostic")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(diag, field, value)
    diag.reviewed_by = admin.user_id
    diag.reviewed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(diag)

    image: ImageUpload | None = None
    if diag.image_id:
        image = await session.get(ImageUpload, diag.image_id)
    return _to_item(diag, image)
