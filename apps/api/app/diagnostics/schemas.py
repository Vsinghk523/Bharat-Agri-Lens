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
