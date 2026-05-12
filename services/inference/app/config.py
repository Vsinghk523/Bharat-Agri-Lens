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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
