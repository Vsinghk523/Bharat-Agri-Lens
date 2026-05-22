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

    # When set, the real predictor pulls the model bundle (ONNX + labels
    # + provenance) from this HuggingFace Hub model repo on first use
    # and caches it under ``hf_model_cache_dir`` for subsequent calls.
    # ``vision_model_uri`` becomes irrelevant when this is set — the
    # downloaded snapshot directory is used directly.
    # Set to e.g. "viveksk523/bal-plantvit-v0" to consume the model
    # produced by the HF Space training pipeline.
    hf_model_repo: str | None = None
    # Write token only required for private model repos. Public model
    # repos download anonymously.
    hf_token: str | None = None
    hf_model_cache_dir: str = "/tmp/bal-plantvit-model"

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
