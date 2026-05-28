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

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
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
from app.jobs.daily_tip import run_daily_tip_job
from app.logging import get_logger
from app.push.service import send_to_user, supports_send
from app.uploads.models import ImageUpload
from app.users.models import User
from app.users.schemas import UserPreferences

log = get_logger(__name__)

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

    # Trigger #1: notify the farmer that their diagnosis was reviewed.
    # Best-effort: any failure here is logged but does NOT roll back the
    # correction or fail the HTTP response.
    await _maybe_send_review_push(session, diag)

    return _to_item(diag, image)


async def _maybe_send_review_push(
    session: AsyncSession,
    diag: PlantDiagnostic,
) -> None:
    """Send 'your scan was reviewed' push if FCM is configured and the
    farmer has notif_diagnoses preference on.

    Kept separate from the route handler so the happy path is readable
    and the push side-effect is easy to swap for a job-queue dispatch
    later (when we want to fan out to many devices without holding the
    HTTP connection)."""
    if not supports_send():
        return
    owner = await session.get(User, diag.user_id)
    if not owner:
        return
    prefs = UserPreferences.from_raw(owner.preferences)
    if not prefs.notif_diagnoses:
        log.info(
            "review_push_skipped_pref_off",
            user_id=diag.user_id,
            diagnostic_id=str(diag.diagnostic_id),
        )
        return

    # Body uses the corrected labels when present, falling back to the
    # model's original prediction. Keeps the notification informative
    # even if the reviewer's only action was confirming a partial.
    plant = diag.correct_plant or diag.plant_classification or "your plant"
    disease = (
        diag.correct_disease
        or diag.disease_name
        or diag.correct_infection_type
        or diag.infection_type
        or "diagnosis"
    )
    title = "Your scan was reviewed"
    body = f"{plant} — {disease}. Tap to see the updated diagnosis."

    sent = await send_to_user(
        session,
        diag.user_id,
        title=title,
        body=body,
        # Mobile reads these to deeplink the user straight to the
        # result page when they tap the notification.
        data={
            "type": "diagnosis_reviewed",
            "diagnostic_id": str(diag.diagnostic_id),
        },
    )
    log.info(
        "review_push_sent",
        user_id=diag.user_id,
        diagnostic_id=str(diag.diagnostic_id),
        delivered=sent,
    )


# ============================================================
# Cron-driven jobs
# ============================================================


@router.post("/cron/daily-tip")
async def trigger_daily_tip(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Fire the daily-tip push fan-out.

    Authentication is via a shared secret (``X-Cron-Secret`` header
    matching ``settings.cron_shared_secret``) rather than admin JWT.
    Cron services don't have OAuth flows; a long random secret is the
    standard pattern here. The endpoint is path-deep and undocumented
    in the OpenAPI tags users see, so it doesn't show up as a "delete
    everything" footgun in the API explorer.

    If the secret is unset on the server, the endpoint refuses every
    call — including from accident. Setting it explicitly is the
    activation step.
    """
    expected = settings.cron_shared_secret
    if not expected or not x_cron_secret or x_cron_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing cron secret",
        )
    result = await run_daily_tip_job(session)
    return result
