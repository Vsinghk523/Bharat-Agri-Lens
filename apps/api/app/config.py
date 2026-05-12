from functools import lru_cache

from pydantic import Field
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

    inference_base_url: str = "http://localhost:8001"
    inference_timeout_seconds: int = 60

    cors_allowed_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
