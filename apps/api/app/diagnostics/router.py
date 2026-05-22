import asyncio
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
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
)
from app.logging import get_logger
from app.services.bhashini import to_bhashini_lang
from app.services.translation import get_translator
from app.users.models import User

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])
settings = get_settings()
log = get_logger(__name__)


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
    prediction: dict = {}
    inference_error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=settings.inference_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.inference_base_url}/predict",
                json={"image_id": str(payload.image_id), "language": payload.language},
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
