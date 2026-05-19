from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "bharat-agri-lens-api"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 30
    cpa_fernet_key: str

    otp_ttl_seconds: int = 300
    otp_rate_limit_per_hour: int = 5
    resend_api_key: str | None = None
    otp_email_from: str = "onboarding@bharatagrilens.in"

    whatsapp_phone_number_id: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_otp_template_name: str = "bal_login_otp"
    whatsapp_otp_template_lang: str = "en"

    s3_bucket: str = "bharat-agri-lens-dev"
    s3_region: str = "ap-south-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_presign_ttl_seconds: int = 300
    # boto3 addressing style:
    #   "auto"    — path style if s3_endpoint_url is set (MinIO/LocalStack), virtual otherwise (AWS)
    #   "path"    — https://endpoint/bucket/key   (MinIO default)
    #   "virtual" — https://bucket.endpoint/key   (AWS, Cloudflare R2, Railway T3)
    s3_addressing_style: str = "auto"
    # Set to true ONLY for backends that reject PutBucketCors (MinIO in
    # CI, LocalStack). Default is to call PutBucketCors at startup so
    # browser PUTs from the SPA work end to end.
    s3_skip_cors_setup: bool = False

    inference_base_url: str = "http://localhost:8001"
    inference_timeout_seconds: int = 60
    # When the inference service is unreachable (timeout, connection
    # refused, 5xx), fall back to a deterministic in-process mock
    # predictor so the diagnostic UI is still demoable. Leave False in
    # real production — silently returning fake plant identifications
    # to a farmer is worse than showing an explicit "service unavailable"
    # message.
    inference_fallback_to_mock: bool = False

    # --- Translation provider selection ---
    # "auto"     — pick first available (Google > Bhashini > mock)
    # "google"   — force Google Cloud Translation (requires GOOGLE_TRANSLATE_API_KEY)
    # "bhashini" — force Bhashini (mocks if BHASHINI_* creds missing)
    # "mock"     — passthrough (data stays in source language; UI labels
    #              still localize via i18next bundles in the SPA)
    translation_provider: str = "auto"

    # Google Cloud Translation v2 (simple API-key auth). Generate at
    # https://console.cloud.google.com/apis/credentials after enabling
    # the "Cloud Translation API" on a Cloud project. 500K chars / month
    # free, ~$20 / million chars beyond. All 22 Indian languages supported.
    google_translate_api_key: str | None = None

    # --- Bhashini (Indian language services gateway) ---
    # Sign up at https://bhashini.gov.in/ to apply for userID + apiKey.
    # When either is empty, the client falls back to mock mode and returns
    # the source text unchanged so the UI doesn't show garbage to users.
    # Bhashini also powers STT / TTS (see app.voice) — those endpoints
    # remain pinned to BhashiniClient regardless of translation_provider.
    bhashini_user_id: str | None = None
    bhashini_api_key: str | None = None
    bhashini_pipeline_id: str = "64392f96daac500b55c543cd"
    bhashini_pipeline_url: str = (
        "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
    )
    bhashini_timeout_seconds: int = 15

    # Background moderation / thumbnail worker
    moderation_enabled: bool = True
    moderation_poll_interval_seconds: int = 10
    moderation_batch_size: int = 5
    moderation_max_image_bytes: int = 10 * 1024 * 1024  # 10 MiB
    thumbnail_max_dim: int = 256
    thumbnail_jpeg_quality: int = 80

    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @field_validator("database_url")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        """Normalize DATABASE_URL to use the asyncpg driver.

        Managed Postgres providers (Railway, Heroku, Supabase, etc.)
        expose the connection string as ``postgresql://`` or
        ``postgres://``. SQLAlchemy defaults to the psycopg2 driver for
        that scheme, but we deploy with asyncpg only. Rewriting the
        scheme here means the URL works whether the operator pastes the
        provider's raw value or the explicit ``postgresql+asyncpg://``
        form.
        """
        if v.startswith("postgresql+asyncpg://"):
            return v
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://") :]
        if v.startswith("postgres://"):  # Heroku-style alias
            return "postgresql+asyncpg://" + v[len("postgres://") :]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
