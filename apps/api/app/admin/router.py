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
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import (
    LabellingQueueItem,
    LabellingQueueResponse,
    LlmFallbackSummaryResponse,
    LlmFallbackSummaryRow,
    ReviewerCorrection,
)
from app.auth.dependencies import get_current_admin
from app.common.errors import NotFoundError
from app.common.s3 import generate_get_url
from app.config import get_settings
from app.db import get_session
from app.diagnostics.models import PlantDiagnostic
from app.jobs.daily_tip import run_daily_tip_job
from app.jobs.export_training_data import run_export_job
from app.jobs.process_treatment_reminders import run_reminder_cron
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
        prediction_source=diag.prediction_source,
    )


@router.get("/labelling-queue", response_model=LabellingQueueResponse)
async def labelling_queue(
    source: str = Query(
        default="flagged",
        pattern="^(flagged|llm_gold)$",
        description=(
            "Which review bucket to fetch: 'flagged' (user said the "
            "diagnosis was incorrect / partial — the original queue) "
            "or 'llm_gold' (Gemini fallback diagnoses the user marked "
            "correct — high-priority candidates for the next training "
            "expansion)."
        ),
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_admin),
) -> LabellingQueueResponse:
    """List diagnostics that need agronomist review.

    Two review buckets, selected via ``source``:

    1. ``flagged`` (default): user marked the diagnosis 'incorrect' or
       'partial'. The model got it wrong (or partially wrong); the
       reviewer's correction goes into ``correct_*`` columns and feeds
       the next training run as gold-label data.

    2. ``llm_gold``: Gemini fallback produced a diagnosis the user
       confirmed as 'correct'. These are the highest-value candidates
       for *expanding* PlantViT's class list — the crop wasn't in our
       model but the LLM nailed it AND the farmer agreed. Agronomist
       verification on these rows is the cheapest path to a new
       trained crop.

    Each item carries the predicted labels (so reviewers see what the
    model thought), a presigned URL to the original image, and any
    corrections an earlier reviewer has already applied — so a second
    pass over the queue can fix mistakes instead of duplicating work.
    """
    base_filter: list = [PlantDiagnostic.deleted_at.is_(None)]
    if source == "llm_gold":
        base_filter += [
            PlantDiagnostic.prediction_source == "llm_fallback",
            PlantDiagnostic.user_feedback == "correct",
        ]
    else:
        base_filter += [PlantDiagnostic.user_feedback.in_(_FLAGGED_VERDICTS)]

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


@router.get(
    "/llm-fallback-summary", response_model=LlmFallbackSummaryResponse
)
async def llm_fallback_summary(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_admin),
) -> LlmFallbackSummaryResponse:
    """Aggregate llm_fallback diagnostics by crop over the last N days.

    This is the operational dashboard for the active-learning flywheel:
    crops that Gemini handled often (and where users frequently said
    "yes that's right") are the highest-value candidates for the next
    PlantViT training expansion. The endpoint returns:

    - Count per crop
    - Feedback breakdown (correct / incorrect / partial / none)
    - Latest occurrence — useful for spotting newly-trending crops
    - Up to 3 sample diagnostic_ids per crop so reviewers can click
      through to see real examples without leaving the dashboard

    Sorted by ``total_count DESC`` so the highest-traffic crops surface
    first. Bound by ``limit`` (default 50) which is plenty — the long
    tail beyond top 50 doesn't have enough volume to be a useful
    training signal yet anyway.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)

    base_filter = [
        PlantDiagnostic.deleted_at.is_(None),
        PlantDiagnostic.prediction_source == "llm_fallback",
        PlantDiagnostic.add_date >= cutoff,
    ]

    # Aggregate: total + feedback-bucket counts + latest_seen + a
    # comma-joined array of up to 3 diagnostic IDs as samples.
    # Postgres-specific ``array_agg`` is fine — we're already
    # PostgreSQL-only for JSONB, encryption, etc.
    from sqlalchemy.dialects.postgresql import array_agg

    stmt = (
        select(
            PlantDiagnostic.plant_classification,
            func.count().label("total_count"),
            func.sum(
                case((PlantDiagnostic.user_feedback == "correct", 1), else_=0)
            ).label("feedback_correct"),
            func.sum(
                case((PlantDiagnostic.user_feedback == "incorrect", 1), else_=0)
            ).label("feedback_incorrect"),
            func.sum(
                case((PlantDiagnostic.user_feedback == "partial", 1), else_=0)
            ).label("feedback_partial"),
            func.sum(
                case((PlantDiagnostic.user_feedback.is_(None), 1), else_=0)
            ).label("feedback_none"),
            func.max(PlantDiagnostic.add_date).label("latest_seen"),
            array_agg(PlantDiagnostic.diagnostic_id).label("all_ids"),
        )
        .where(*base_filter, PlantDiagnostic.plant_classification.is_not(None))
        .group_by(PlantDiagnostic.plant_classification)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()

    items: list[LlmFallbackSummaryRow] = []
    for r in rows:
        # Slice to 3 samples — keeps response size bounded even when
        # a crop has thousands of rows.
        sample_ids = list(r.all_ids or [])[:3]
        items.append(
            LlmFallbackSummaryRow(
                plant_classification=r.plant_classification,
                total_count=int(r.total_count),
                feedback_correct=int(r.feedback_correct or 0),
                feedback_incorrect=int(r.feedback_incorrect or 0),
                feedback_partial=int(r.feedback_partial or 0),
                feedback_none=int(r.feedback_none or 0),
                latest_seen=r.latest_seen,
                sample_diagnostic_ids=sample_ids,
            )
        )

    # Total fallback row count for the period — header stat.
    total_stmt = (
        select(func.count()).select_from(PlantDiagnostic).where(*base_filter)
    )
    total = int((await session.execute(total_stmt)).scalar_one())

    return LlmFallbackSummaryResponse(
        items=items,
        window_days=days,
        total_fallback_rows=total,
    )


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


@router.post("/cron/export-training-data")
async def trigger_training_data_export(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run the active-learning data-export job.

    Builds an HF Datasets bundle of every reviewed diagnostic since
    the last successful export, pushes it to the configured HF Hub
    repo, and advances the watermark. Idempotent — running twice in a
    day produces an empty dataset the second time (no new rows
    since the first run).

    Auth: same X-Cron-Secret pattern as /admin/cron/daily-tip. Set
    ``CRON_SHARED_SECRET`` on Railway and have a Railway cron service
    POST here on whatever schedule you want (daily / weekly).
    """
    expected = settings.cron_shared_secret
    if not expected or not x_cron_secret or x_cron_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing cron secret",
        )
    return await run_export_job(session)


@router.post("/cron/process-treatment-reminders")
async def trigger_treatment_reminders_cron(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Fire any due, pending treatment_reminders rows.

    Designed to be called hourly by a Railway cron service. Picks up
    reminders where ``scheduled_at <= now() AND status='pending' AND
    dismissed_at IS NULL``, sends FCM push, flips status to 'sent'.

    Re-checks the user's notif_treatment_reminders preference at fire
    time so a Settings flip after scheduling takes effect on the next
    tick (and the row is moved to 'dismissed' rather than left
    pending forever).
    """
    expected = settings.cron_shared_secret
    if not expected or not x_cron_secret or x_cron_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing cron secret",
        )
    return await run_reminder_cron(session)
