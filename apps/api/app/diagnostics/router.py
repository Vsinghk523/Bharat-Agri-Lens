import asyncio
import uuid
from datetime import UTC, date, datetime

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.common.errors import NotFoundError
from app.config import get_settings
from app.db import get_session
from app.diagnostics.mock_predictor import mock_predict
from app.diagnostics.models import DiagnosticFollowupQuestion, PlantDiagnostic
from app.diagnostics.schemas import (
    DiagnosticCreate,
    DiagnosticRead,
    DiagnosticUpdate,
    FeedbackCreate,
    FollowupCreate,
    FollowupRead,
    TreatmentProgressRead,
)
from app.logging import get_logger
from app.reminders.schedule import _INTERVAL_DAYS, schedule_reminders_for_diagnosis
from app.services.bhashini import to_bhashini_lang
from app.services.translation import get_translator
from app.users.models import User
from app.users.schemas import UserPreferences

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])
settings = get_settings()
log = get_logger(__name__)

# Per-user daily cap on LLM-fallback diagnoses. The fallback path is
# meant for the long tail of crops our specialist model doesn't yet
# cover; bounding it protects both Gemini API spend and against a
# single user trying to spam the system. Tunable via env later if we
# want to A/B different caps for paid tiers.
LLM_FALLBACK_DAILY_QUOTA = 5


async def _llm_fallback_used_today(
    session: AsyncSession, user_id: str
) -> int:
    """How many ``llm_fallback`` predictions this user already got today.

    Cheap query: indexed on user_id + add_date, filtered to the small
    prediction_source='llm_fallback' subset. Run once per
    /diagnostics POST so cost is bounded.
    """
    today = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
    result = await session.execute(
        select(func.count(PlantDiagnostic.diagnostic_id)).where(
            PlantDiagnostic.user_id == user_id,
            PlantDiagnostic.prediction_source == "llm_fallback",
            PlantDiagnostic.add_date >= today,
        )
    )
    return int(result.scalar_one() or 0)


async def _localized_read(
    diag: PlantDiagnostic, target_bcp47: str | None
) -> DiagnosticRead:
    """Return a DiagnosticRead with user-facing text fields translated.

    The database row stays canonical English; translation happens on
    the way out so the user can switch languages and re-render any
    historical diagnostic without re-running inference.
    """
    base = DiagnosticRead.model_validate(diag)
    tgt = to_bhashini_lang(target_bcp47)
    if tgt == "en":
        return base
    translator = get_translator()
    translated = await translator.translate_many(
        [
            base.plant_classification,
            base.disease_name,
            base.suggested_remedies,
            base.preventive_measures,
        ],
        "en",
        tgt,
    )
    return base.model_copy(
        update={
            "plant_classification": translated[0],
            "disease_name": translated[1],
            "suggested_remedies": translated[2],
            "preventive_measures": translated[3],
        }
    )


async def _localized_followup(
    row: DiagnosticFollowupQuestion, target_bcp47: str | None
) -> FollowupRead:
    base = FollowupRead.model_validate(row)
    tgt = to_bhashini_lang(target_bcp47)
    if tgt == "en":
        return base
    new_text = await get_translator().translate(base.question_text, "en", tgt)
    return base.model_copy(update={"question_text": new_text})


@router.post("", response_model=DiagnosticRead, status_code=status.HTTP_201_CREATED)
async def create_diagnostic(
    payload: DiagnosticCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PlantDiagnostic:
    """Trigger inference for an uploaded image and persist the diagnostic."""
    # Quota gate for the Gemini LLM fallback. The inference service
    # itself is happy to call Gemini whenever its OOD layer trips a
    # salvageable rejection; we sit in front of that and refuse to
    # let it (``skip_llm_fallback=True``) when the user has already
    # used their daily allowance. Hitting the cap means the original
    # OOD rejection card is shown to the farmer — same UX as before
    # the fallback layer existed, capped per-user.
    used_today = await _llm_fallback_used_today(session, current_user.user_id)
    skip_llm_fallback = used_today >= LLM_FALLBACK_DAILY_QUOTA
    if skip_llm_fallback:
        log.info(
            "llm_fallback_quota_exhausted",
            user_id=current_user.user_id,
            used_today=used_today,
            quota=LLM_FALLBACK_DAILY_QUOTA,
        )

    prediction: dict = {}
    inference_error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=settings.inference_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.inference_base_url}/predict",
                json={
                    "image_id": str(payload.image_id),
                    "language": payload.language,
                    "skip_llm_fallback": skip_llm_fallback,
                },
            )
            if resp.status_code < 400:
                prediction = resp.json()
            else:
                inference_error = f"http_{resp.status_code}"
    except httpx.HTTPError as exc:
        inference_error = type(exc).__name__

    if not prediction and settings.inference_fallback_to_mock:
        # The dedicated inference service isn't reachable, but the operator
        # has opted into the in-process mock. Useful for demos before the
        # GPU-backed predictor is provisioned.
        log.warning(
            "inference_fallback_to_mock",
            image_id=str(payload.image_id),
            inference_base_url=settings.inference_base_url,
            inference_error=inference_error,
        )
        prediction = mock_predict(str(payload.image_id), payload.language)
    elif not prediction:
        log.warning(
            "inference_unavailable",
            image_id=str(payload.image_id),
            inference_base_url=settings.inference_base_url,
            inference_error=inference_error,
        )

    diag = PlantDiagnostic(
        user_id=current_user.user_id,
        image_id=payload.image_id,
        plant_classification=prediction.get("plant_classification"),
        scientific_name=prediction.get("scientific_name"),
        disease_name=prediction.get("disease_name"),
        pathogen_name=prediction.get("pathogen_name"),
        infection_type=prediction.get("infection_type"),
        severity=prediction.get("severity"),
        confidence_score=prediction.get("confidence_score"),
        secondary_predictions=prediction.get("secondary_predictions"),
        suggested_remedies=prediction.get("suggested_remedies"),
        chemical_remedies=prediction.get("chemical_remedies"),
        organic_remedies=prediction.get("organic_remedies"),
        preventive_measures=prediction.get("preventive_measures"),
        # OOD-defense fields. Both NULL on a normal diagnosis; set
        # together when the inference layer refused (too_blurry,
        # not_a_plant, low_confidence, etc.). See
        # services/inference/app/ood.py.
        rejection_reason=prediction.get("rejection_reason"),
        rejection_hint=prediction.get("rejection_hint"),
        # Provenance: 'plantvit' is the model default; 'llm_fallback'
        # set by the inference service when Gemini was used because
        # the specialist rejected; 'mock' for dev. Stored explicitly
        # so analytics + the UI badge can branch on it without
        # re-inferring source from other fields.
        prediction_source=prediction.get("prediction_source") or "plantvit",
        # Defensive truncation: the column is VARCHAR(128) per migration
        # 0004 which fits everything we ship today, but the predictor
        # is operator-configurable and a future provenance.json could
        # carry a backbone name long enough to overflow. Truncating here
        # is safer than crashing the whole diagnostic INSERT.
        model_version=(prediction.get("model_version") or "")[:128] or None,
        language_used=payload.language,
    )
    session.add(diag)
    await session.flush()

    for idx, q in enumerate(prediction.get("followup_questions", []) or []):
        session.add(
            DiagnosticFollowupQuestion(
                diagnostic_id=diag.diagnostic_id,
                question_text=q.get("text", ""),
                question_language=q.get("language", payload.language),
                category=q.get("category"),
                display_order=idx,
            )
        )

    # Trigger #2 — schedule treatment reminders. Internal policy decides
    # whether to schedule (skips low-severity, unknown infection types,
    # rejections, and users who've disabled the preference). Inserted
    # in the same transaction as the diagnostic so a commit failure
    # rolls back the reminders too.
    prefs = UserPreferences.from_raw(current_user.preferences).model_dump()
    await schedule_reminders_for_diagnosis(session, diag, prefs)

    await session.commit()
    await session.refresh(diag)
    return await _localized_read(diag, payload.language)


@router.get("/{diagnostic_id}", response_model=DiagnosticRead)
async def get_diagnostic(
    diagnostic_id: uuid.UUID,
    language: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRead:
    """Fetch a single diagnostic, optionally re-localized.

    ``language`` is the BCP-47 code the client wants to render in
    (``hi-IN``, ``ta-IN``, …). When omitted we fall back to the user's
    saved preference. The query-param override lets the frontend
    language switcher re-translate without persisting a change to the
    user row on every dropdown toggle.
    """
    obj = await session.get(PlantDiagnostic, diagnostic_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("Diagnostic")
    target = language or current_user.preferred_language
    return await _localized_read(obj, target)


@router.get(
    "/{diagnostic_id}/treatment-progress",
    response_model=TreatmentProgressRead,
)
async def get_treatment_progress(
    diagnostic_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TreatmentProgressRead:
    """Where the farmer is in the 3-step treatment cycle.

    Powers the Home page's active-issue hero, which shows
    "Step N of 3 - Next spray in X days" so the farmer can tell
    at a glance how far through the spray cycle they are.

    Behaviour:
    - ``total_steps == 0`` when no reminders were ever scheduled
      (viral / abiotic / weed_competition / low-severity / user
      opted out). The UI hides the indicator in that case.
    - ``completed_steps`` counts only rows with ``status == 'sent'``.
      Dismissed and failed rows do not count as completed.
    - ``next_scheduled_at`` is the ``scheduled_at`` of the earliest
      still-pending row, or null when the cycle is finished or
      dismissed entirely.

    Authorization: 404 (treated identically to "doesn't exist") if
    the diagnostic belongs to a different user. Avoids leaking row
    existence to unrelated callers.
    """
    from app.reminders.models import TreatmentReminder

    diag = await session.get(PlantDiagnostic, diagnostic_id)
    if (
        not diag
        or diag.deleted_at is not None
        or diag.user_id != current_user.user_id
    ):
        raise NotFoundError("Diagnostic")

    result = await session.execute(
        select(TreatmentReminder)
        .where(TreatmentReminder.diagnostic_id == diagnostic_id)
        .order_by(TreatmentReminder.step_no)
    )
    reminders = list(result.scalars().all())

    if not reminders:
        # Nothing was ever scheduled. Surface zeros so the UI can
        # hide the indicator without a separate "has_reminders" flag.
        return TreatmentProgressRead(
            total_steps=0,
            completed_steps=0,
            current_step=0,
            next_scheduled_at=None,
            interval_days=_INTERVAL_DAYS.get(diag.infection_type or ""),
        )

    total = len(reminders)
    completed = sum(1 for r in reminders if r.status == "sent")
    # current_step is 1-indexed and capped at total — when the whole
    # cycle is sent, we still want to display "Step 3 of 3 - complete"
    # rather than "Step 4 of 3".
    current = min(completed + 1, total)
    next_scheduled = next(
        (r.scheduled_at for r in reminders if r.status == "pending"),
        None,
    )
    return TreatmentProgressRead(
        total_steps=total,
        completed_steps=completed,
        current_step=current,
        next_scheduled_at=next_scheduled,
        interval_days=_INTERVAL_DAYS.get(diag.infection_type or ""),
    )


@router.delete(
    "/{diagnostic_id}/reminders",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def dismiss_reminders(
    diagnostic_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Cancel all pending treatment reminders for this diagnostic.

    Idempotent: safe to call twice. Already-sent reminders stay 'sent'
    (the dismissal is forward-looking only). Already-dismissed rows
    aren't re-stamped.

    Authorization: the diagnostic must belong to the caller. Treats
    'doesn't exist' and 'belongs to someone else' identically to
    avoid leaking diagnostic-existence to unrelated users.
    """
    from sqlalchemy import update

    from app.reminders.models import TreatmentReminder

    diag = await session.get(PlantDiagnostic, diagnostic_id)
    if not diag or diag.deleted_at is not None or diag.user_id != current_user.user_id:
        raise NotFoundError("Diagnostic")

    now = datetime.now(UTC)
    await session.execute(
        update(TreatmentReminder)
        .where(
            TreatmentReminder.diagnostic_id == diagnostic_id,
            TreatmentReminder.status == "pending",
        )
        .values(status="dismissed", dismissed_at=now)
    )
    await session.commit()


@router.get("", response_model=list[DiagnosticRead])
async def list_diagnostics(
    limit: int = 50,
    offset: int = 0,
    language: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[DiagnosticRead]:
    stmt = (
        select(PlantDiagnostic)
        .where(
            PlantDiagnostic.deleted_at.is_(None),
            PlantDiagnostic.user_id == current_user.user_id,
        )
        .order_by(PlantDiagnostic.add_date.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    target = language or current_user.preferred_language
    return await asyncio.gather(*(_localized_read(r, target) for r in rows))


@router.patch("/{diagnostic_id}", response_model=DiagnosticRead)
async def update_diagnostic(
    diagnostic_id: uuid.UUID,
    payload: DiagnosticUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRead:
    obj = await session.get(PlantDiagnostic, diagnostic_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("Diagnostic")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await session.commit()
    await session.refresh(obj)
    return await _localized_read(obj, current_user.preferred_language)


@router.delete("/{diagnostic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_diagnostic(
    diagnostic_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    obj = await session.get(PlantDiagnostic, diagnostic_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("Diagnostic")
    obj.status = "Inactive"
    obj.deleted_at = datetime.now(UTC)
    await session.commit()


@router.post("/{diagnostic_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def submit_feedback(
    diagnostic_id: uuid.UUID,
    payload: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    obj = await session.get(PlantDiagnostic, diagnostic_id)
    if not obj or obj.deleted_at is not None or obj.user_id != current_user.user_id:
        raise NotFoundError("Diagnostic")
    obj.user_feedback = payload.verdict
    await session.commit()


# --- Follow-up questions ---


async def _user_owns_diagnostic(
    session: AsyncSession, diagnostic_id: uuid.UUID, user_id: str
) -> bool:
    diag = await session.get(PlantDiagnostic, diagnostic_id)
    return bool(diag and diag.deleted_at is None and diag.user_id == user_id)


@router.get("/{diagnostic_id}/followups", response_model=list[FollowupRead])
async def list_followups(
    diagnostic_id: uuid.UUID,
    language: str | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[FollowupRead]:
    if not await _user_owns_diagnostic(session, diagnostic_id, current_user.user_id):
        raise NotFoundError("Diagnostic")
    stmt = (
        select(DiagnosticFollowupQuestion)
        .where(
            DiagnosticFollowupQuestion.diagnostic_id == diagnostic_id,
            DiagnosticFollowupQuestion.deleted_at.is_(None),
        )
        .order_by(DiagnosticFollowupQuestion.display_order.asc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    target = language or current_user.preferred_language
    return await asyncio.gather(*(_localized_followup(r, target) for r in rows))


@router.post("/followups", response_model=FollowupRead, status_code=status.HTTP_201_CREATED)
async def create_followup(
    payload: FollowupCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> DiagnosticFollowupQuestion:
    if not await _user_owns_diagnostic(session, payload.diagnostic_id, current_user.user_id):
        raise NotFoundError("Diagnostic")
    record = DiagnosticFollowupQuestion(
        diagnostic_id=payload.diagnostic_id,
        question_text=payload.question_text,
        question_language=payload.question_language,
        category=payload.category,
        display_order=payload.display_order,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.post("/followups/{addnl_question_id}/click", status_code=status.HTTP_204_NO_CONTENT)
async def mark_followup_clicked(
    addnl_question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    obj = await session.get(DiagnosticFollowupQuestion, addnl_question_id)
    if not obj:
        raise NotFoundError("Followup")
    if not await _user_owns_diagnostic(session, obj.diagnostic_id, current_user.user_id):
        raise NotFoundError("Followup")
    obj.was_clicked = True
    await session.commit()


@router.delete("/followups/{addnl_question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_followup(
    addnl_question_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    obj = await session.get(DiagnosticFollowupQuestion, addnl_question_id)
    if not obj or obj.deleted_at is not None:
        raise NotFoundError("Followup")
    if not await _user_owns_diagnostic(session, obj.diagnostic_id, current_user.user_id):
        raise NotFoundError("Followup")
    obj.status = "Inactive"
    obj.deleted_at = datetime.now(UTC)
    await session.commit()
