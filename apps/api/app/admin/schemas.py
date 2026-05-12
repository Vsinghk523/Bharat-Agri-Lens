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
