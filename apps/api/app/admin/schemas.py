import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class LabellingQueueItem(BaseModel):
    diagnostic_id: uuid.UUID
    image_id: uuid.UUID | None
    image_url: str | None
    storage_location: str | None
    predicted_plant: str | None
    predicted_disease: str | None
    predicted_infection_type: str | None
    confidence_score: Decimal | None
    user_feedback: str
    language_used: str | None
    add_date: datetime
    modify_date: datetime
    # Where the prediction came from. Lets the queue UI show a
    # "General AI" badge on llm_fallback rows so the reviewer
    # immediately sees these are coverage-expansion candidates, not
    # PlantViT failures.
    prediction_source: str = "plantvit"

    # Reviewer's correction, null until an admin has hit the PATCH
    # endpoint with their authoritative labels.
    correct_plant: str | None = None
    correct_disease: str | None = None
    correct_infection_type: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class LabellingQueueResponse(BaseModel):
    items: list[LabellingQueueItem]
    total: int
    limit: int
    offset: int


class ReviewerCorrection(BaseModel):
    """Reviewer's authoritative re-label. All fields optional so a
    reviewer can correct just one axis (e.g. swap the infection type
    while leaving the crop label alone)."""

    correct_plant: str | None = Field(None, max_length=100)
    correct_disease: str | None = Field(None, max_length=150)
    correct_infection_type: str | None = Field(None, max_length=30)


class LlmFallbackSummaryRow(BaseModel):
    """One row per (plant_classification) aggregated from llm_fallback
    diagnostics over the requested time window."""

    plant_classification: str
    total_count: int
    feedback_correct: int
    feedback_incorrect: int
    feedback_partial: int
    feedback_none: int
    latest_seen: datetime
    sample_diagnostic_ids: list[uuid.UUID] = Field(default_factory=list)


class LlmFallbackSummaryResponse(BaseModel):
    items: list[LlmFallbackSummaryRow]
    window_days: int
    total_fallback_rows: int
