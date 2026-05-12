"""Admin / data-ops endpoints.

The labelling queue is the entry point for the active-learning loop:
every diagnostic the user flagged ``incorrect`` or ``partial`` is a
candidate for human re-labelling. Reviewers pull this queue weekly,
re-label, and the corrected data feeds back into ``services/training/``
on the next run.

Gating: the endpoint is currently behind the standard Bearer guard —
any authenticated user can see all flagged diagnostics, INCLUDING
those from other users. That's deliberately permissive for v1
because the alternative (per-user filtering) defeats the whole
"global review queue" point. Tightening this to admin-only is
tracked as a TODO and needs the role-based auth work that's also
gating ``DELETE /users/{id}/purge``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import LabellingQueueItem, LabellingQueueResponse
from app.auth.dependencies import get_current_user
from app.common.s3 import generate_get_url
from app.config import get_settings
from app.db import get_session
from app.diagnostics.models import PlantDiagnostic
from app.uploads.models import ImageUpload
from app.users.models import User

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()

_FLAGGED_VERDICTS = ("incorrect", "partial")


@router.get("/labelling-queue", response_model=LabellingQueueResponse)
async def labelling_queue(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> LabellingQueueResponse:
    """List diagnostics the user marked incorrect / partial.

    Each item carries the predicted labels (so reviewers can see what
    the model thought) plus a presigned URL to the original image (so
    they can see what the model was looking at). Filtering by
    ``deleted_at IS NULL`` and ``user_feedback IN (...)`` is enforced
    at the database level so cancelled / un-flagged rows never appear.
    """
    base_filter = [
        PlantDiagnostic.deleted_at.is_(None),
        PlantDiagnostic.user_feedback.in_(_FLAGGED_VERDICTS),
    ]

    total_stmt = select(func.count()).select_from(PlantDiagnostic).where(*base_filter)
    total = int((await session.execute(total_stmt)).scalar_one())

    # Pull both rows in a single query so we avoid an N+1 against image_uploads.
    rows_stmt = (
        select(PlantDiagnostic, ImageUpload)
        .outerjoin(ImageUpload, ImageUpload.image_id == PlantDiagnostic.image_id)
        .where(*base_filter)
        .order_by(PlantDiagnostic.modify_date.desc())
        .limit(limit)
        .offset(offset)
    )
    pairs = (await session.execute(rows_stmt)).all()

    items: list[LabellingQueueItem] = []
    for diag, image in pairs:
        url: str | None = None
        if image is not None and image.storage_location:
            try:
                url = generate_get_url(
                    image.storage_location, settings.s3_presign_ttl_seconds
                )
            except Exception:  # noqa: BLE001
                # Presign helpers can fail when the S3 client isn't reachable
                # in test / offline mode — that shouldn't break the queue.
                url = None

        items.append(
            LabellingQueueItem(
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
            )
        )

    return LabellingQueueResponse(items=items, total=total, limit=limit, offset=offset)
