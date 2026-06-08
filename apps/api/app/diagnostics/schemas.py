import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiagnosticCreate(BaseModel):
    image_id: uuid.UUID
    language: str = "en-IN"


class DiagnosticUpdate(BaseModel):
    plant_classification: str | None = None
    disease_name: str | None = None
    infection_type: str | None = None
    suggested_remedies: str | None = None
    user_feedback: str | None = None


class DiagnosticRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    diagnostic_id: uuid.UUID
    user_id: str
    image_id: uuid.UUID | None
    plant_classification: str | None
    scientific_name: str | None
    disease_name: str | None
    pathogen_name: str | None
    infection_type: str | None
    severity: str | None
    confidence_score: Decimal | None
    # JSONB columns may hold either an object or an array; accept both.
    secondary_predictions: list[dict[str, Any]] | dict[str, Any] | None
    suggested_remedies: str | None
    chemical_remedies: list[dict[str, Any]] | dict[str, Any] | None
    organic_remedies: list[dict[str, Any]] | dict[str, Any] | None
    preventive_measures: str | None
    language_used: str | None
    user_feedback: str | None
    status: str
    add_date: datetime
    model_version: str | None
    # OOD-defense: set when the inference layer refused to diagnose.
    # See services/inference/app/ood.py for the canonical values.
    rejection_reason: str | None = None
    rejection_hint: str | None = None
    # Source of this prediction: ``plantvit`` (specialist model),
    # ``llm_fallback`` (Gemini, used when the specialist rejected),
    # or ``mock`` (dev only). Default ``plantvit`` for back-compat.
    prediction_source: str = "plantvit"


class TreatmentProgressRead(BaseModel):
    """Where the farmer is in the 3-step treatment cycle for a diagnosis.

    Returned by ``GET /diagnostics/{id}/treatment-progress`` so the
    Home page's active-issue hero can show "Step N of 3" + a "next
    spray in X days" line.

    The "no reminders exist" case (viral / abiotic / weed_competition
    diagnoses, low-severity, or the user dismissed them) is signalled
    by ``total_steps == 0`` — that lets the UI hide the indicator
    without a separate has-reminders flag.
    """

    total_steps: int = Field(
        ...,
        description=(
            "How many treatment_reminders rows exist for this "
            "diagnostic. Zero means no cycle was scheduled (viral, "
            "low-severity, user opted out, etc.) — UI should hide "
            "the progress indicator."
        ),
    )
    completed_steps: int = Field(
        ...,
        description="Reminders with status='sent'. 0..total_steps.",
    )
    current_step: int = Field(
        ...,
        description=(
            "1-indexed step the farmer is currently on. Equals "
            "min(completed_steps + 1, total_steps). When the whole "
            "cycle is done (completed_steps == total_steps) this "
            "still reads as total_steps — the UI uses the "
            "completed/total ratio to decide whether to show "
            "'complete' vs 'in progress'."
        ),
    )
    next_scheduled_at: datetime | None = Field(
        default=None,
        description=(
            "scheduled_at of the earliest still-pending reminder, "
            "or null when the whole cycle has fired."
        ),
    )
    interval_days: int | None = Field(
        default=None,
        description=(
            "Days between successive sprays for this infection type "
            "(fungal=7, bacterial=5, insect_pest=10, etc.). Used by "
            "the UI to render 'Next spray in X days' even when the "
            "cron hasn't yet computed next_scheduled_at."
        ),
    )


class FollowupCreate(BaseModel):
    diagnostic_id: uuid.UUID
    question_text: str
    question_language: str = "en-IN"
    category: str | None = None
    display_order: int = Field(default=0, ge=0)


class FollowupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    addnl_question_id: uuid.UUID
    diagnostic_id: uuid.UUID
    question_text: str
    question_language: str | None
    display_order: int
    category: str | None
    was_clicked: bool
    answer_cache: str | None


class FeedbackCreate(BaseModel):
    verdict: str = Field(..., description="correct | incorrect | partial")
    notes: str | None = None
