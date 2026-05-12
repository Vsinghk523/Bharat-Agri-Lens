"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _audit_cols() -> list[sa.Column]:
    return [
        sa.Column("add_user", sa.String(10), nullable=True),
        sa.Column("add_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("modify_user", sa.String(10), nullable=True),
        sa.Column("modify_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("status", sa.String(10), nullable=False, server_default="Active"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(10), primary_key=True),
        sa.Column("user_name", sa.String(100)),
        sa.Column("user_email", sa.String(100), unique=True),
        sa.Column("isd_code", sa.CHAR(2), nullable=False),
        sa.Column("mobile_no", sa.BigInteger, nullable=False, unique=True),
        sa.Column("address", sa.String(200)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(50)),
        sa.Column("country", sa.CHAR(2)),
        sa.Column("user_type", sa.String(20), nullable=False, server_default="Farmer"),
        sa.Column("preferred_language", sa.CHAR(5), nullable=False, server_default="en-IN"),
        sa.Column("kyc_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.String(30)),
        sa.Column("consent_version", sa.String(10)),
        sa.Column("referral_source", sa.String(50)),
        sa.Column("default_crop_interest", sa.String(100)),
        sa.Column("geo_lat", sa.Numeric(9, 6)),
        sa.Column("geo_lng", sa.Numeric(9, 6)),
        *_audit_cols(),
    )
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "otp_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mobile_no", sa.BigInteger),
        sa.Column("email", sa.String(120)),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("otp_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("delivery_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requester_ip", sa.String(45)),
    )
    op.create_index("ix_otp_email", "otp_attempts", ["email"])
    op.create_index("ix_otp_mobile", "otp_attempts", ["mobile_no"])

    op.create_table(
        "consent_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(10), nullable=False),
        sa.Column("consent_version", sa.String(10), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(300)),
    )
    op.create_index("ix_consent_user", "consent_log", ["user_id"])

    op.create_table(
        "image_uploads",
        sa.Column("image_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(10), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("image_name", sa.String(50), nullable=False),
        sa.Column("image_file_type", sa.String(10), nullable=False),
        sa.Column("storage_location", sa.String(200), nullable=False),
        sa.Column("content_hash", sa.CHAR(64)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("mime_type", sa.String(50)),
        sa.Column("exif_captured_at", sa.String(40)),
        sa.Column("exif_lat", sa.String(30)),
        sa.Column("exif_lng", sa.String(30)),
        sa.Column("moderation_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("thumbnail_location", sa.String(200)),
        *_audit_cols(),
    )
    op.create_index("ix_image_uploads_user", "image_uploads", ["user_id"])
    op.create_index("ix_image_uploads_hash", "image_uploads", ["content_hash"])

    op.create_table(
        "plant_diagnostics",
        sa.Column("diagnostic_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(10), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("image_uploads.image_id")),
        sa.Column("plant_classification", sa.String(100)),
        sa.Column("scientific_name", sa.String(150)),
        sa.Column("disease_name", sa.String(150)),
        sa.Column("pathogen_name", sa.String(150)),
        sa.Column("infection_type", sa.String(30)),
        sa.Column("severity", sa.String(10)),
        sa.Column("confidence_score", sa.Numeric(5, 4)),
        sa.Column("secondary_predictions", postgresql.JSONB),
        sa.Column("model_version", sa.String(50)),
        sa.Column("suggested_remedies", sa.Text),
        sa.Column("chemical_remedies", postgresql.JSONB),
        sa.Column("organic_remedies", postgresql.JSONB),
        sa.Column("preventive_measures", sa.Text),
        sa.Column("language_used", sa.CHAR(5)),
        sa.Column("user_feedback", sa.String(20)),
        *_audit_cols(),
    )
    op.create_index("ix_diag_user", "plant_diagnostics", ["user_id"])
    op.create_index("ix_diag_infection_type", "plant_diagnostics", ["infection_type"])

    op.create_table(
        "diagnostic_followup_questions",
        sa.Column("addnl_question_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "diagnostic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plant_diagnostics.diagnostic_id"),
            nullable=False,
        ),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("question_language", sa.CHAR(5)),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("category", sa.String(30)),
        sa.Column("was_clicked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("answer_cache", sa.Text),
        *_audit_cols(),
    )
    op.create_index("ix_followup_diag", "diagnostic_followup_questions", ["diagnostic_id"])

    op.create_table(
        "chat_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(10), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("language", sa.CHAR(5), nullable=False, server_default="en-IN"),
        *_audit_cols(),
    )
    op.create_index("ix_chat_sessions_user", "chat_sessions", ["user_id"])

    op.create_table(
        "chat_messages",
        sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chat_sessions.session_id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("language", sa.CHAR(5), nullable=False, server_default="en-IN"),
        sa.Column("content_text", sa.Text),
        sa.Column("audio_blob_url", sa.String(300)),
        sa.Column("transcription", sa.Text),
        sa.Column("tokens_used", sa.Integer),
        *_audit_cols(),
    )
    op.create_index("ix_chat_messages_session", "chat_messages", ["session_id"])

    op.create_table(
        "data_source_registry",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_name", sa.String(150), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("license", sa.String(100)),
        sa.Column("category", sa.String(50)),  # research / govt / ngo / commercial
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.Column("scrape_status", sa.String(20)),
        sa.Column("notes", sa.Text),
        *_audit_cols(),
    )

    op.create_table(
        "model_registry",
        sa.Column("model_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("artifact_url", sa.String(300), nullable=False),
        sa.Column("training_data_hash", sa.CHAR(64)),
        sa.Column("eval_metrics", postgresql.JSONB),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        *_audit_cols(),
        sa.UniqueConstraint("model_name", "model_version", name="uq_model_name_version"),
    )

    op.create_table(
        "pesticide_catalog",
        sa.Column("pesticide_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("active_ingredient", sa.String(200)),
        sa.Column("target_pathogens", postgresql.JSONB),
        sa.Column("dose_min", sa.Numeric(10, 4)),
        sa.Column("dose_max", sa.Numeric(10, 4)),
        sa.Column("dose_unit", sa.String(20)),
        sa.Column("phi_days", sa.Integer),  # pre-harvest interval
        sa.Column("cibrc_approved", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("category", sa.String(20)),  # chemical / organic / biological
        *_audit_cols(),
    )


def downgrade() -> None:
    for tbl in [
        "pesticide_catalog",
        "model_registry",
        "data_source_registry",
        "chat_messages",
        "chat_sessions",
        "diagnostic_followup_questions",
        "plant_diagnostics",
        "image_uploads",
        "consent_log",
        "otp_attempts",
        "users",
    ]:
        op.drop_table(tbl)
