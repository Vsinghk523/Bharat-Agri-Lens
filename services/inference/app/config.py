from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 8001
    environment: str = "development"
    log_level: str = "INFO"

    vision_model_uri: str = "stub"
    vision_model_version: str = "plantvit-v0-stub"
    llm_model_name: str = "gemma-2-9b-it"
    llm_adapter_uri: str | None = None

    use_mock_predictor: bool = True

    # --- S3 / object storage (real-predictor only) ---
    # Must match the API service so we read from the same bucket prefix
    # the presign endpoint writes to.
    s3_bucket: str = "bharat-agri-lens-dev"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
