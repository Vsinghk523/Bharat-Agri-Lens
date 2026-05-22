import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CHAR, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import AuditMixin, Base


class PlantDiagnostic(AuditMixin, Base):
    __tablename__ = "plant_diagnostics"

    diagnostic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(10), ForeignKey("users.user_id"), index=True)
    image_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("image_uploads.image_id"), nullable=True
    )

    plant_classification: Mapped[str | None] = mapped_column(String(100))
    scientific_name: Mapped[str | None] = mapped_column(String(150))
    disease_name: Mapped[str | None] = mapped_column(String(150))
    pathogen_name: Mapped[str | None] = mapped_column(String(150))
    # insect_pest | fungal | viral | bacterial | nematode | nutrient_deficiency
    # | abiotic_stress | weed_competition | unknown
    infection_type: Mapped[str | None] = mapped_column(String(30), index=True)

    severity: Mapped[str | None] = mapped_column(String(10))  # low/medium/high/critical
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    secondary_predictions: Mapped[dict | None] = mapped_column(JSONB)
    # 128 chars covers ``<config-name>-<backbone-with-slashes-replaced>``
    # patterns even when the backbone name is long (the real predictor
    # emits e.g. ``plantvit-v0-plantvillage-google_vit-base-patch16-224``
    # which alone is 52 chars). Stay in sync with migration 0004.
    model_version: Mapped[str | None] = mapped_column(String(128))

    suggested_remedies: Mapped[str | None] = mapped_column(Text)
    chemical_remedies: Mapped[dict | None] = mapped_column(JSONB)
    organic_remedies: Mapped[dict | None] = mapped_column(JSONB)
    preventive_measures: Mapped[str | None] = mapped_column(Text)

    language_used: Mapped[str | None] = mapped_column(CHAR(5))
    user_feedback: Mapped[str | None] = mapped_column(String(20))

    # Reviewer's authoritative re-label. NULL until an admin has
    # corrected the diagnosis via /admin/labelling-queue/{id}.
    # When non-null, these are the labels the next training run picks
    # up; the model's own predicted_* fields stay untouched for audit.
    correct_plant: Mapped[str | None] = mapped_column(String(100))
    correct_disease: Mapped[str | None] = mapped_column(String(150))
    correct_infection_type: Mapped[str | None] = mapped_column(String(30))
    reviewed_by: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("users.user_id"), index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DiagnosticFollowupQuestion(AuditMixin, Base):
    __tablename__ = "diagnostic_followup_questions"

    addnl_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    diagnostic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plant_diagnostics.diagnostic_id"), index=True
    )
    question_text: Mapped[str] = mapped_column(Text)
    question_language: Mapped[str | None] = mapped_column(CHAR(5))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    # cost | dosage | timing | alternative | prevention | escalation
    category: Mapped[str | None] = mapped_column(String(30))
    was_clicked: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_cache: Mapped[str | None] = mapped_column(Text)
