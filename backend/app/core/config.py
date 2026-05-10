from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Targeted File Review API"
    app_version: str = "0.1.0"
    environment: str = "local"
    chat_model: str = "openai:gpt-5.4-nano"
    audit_model: str = "openai:gpt-5.4-nano"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    data_dir: Path = Path("data")
    database_url: str = "sqlite+aiosqlite:///data/tfr_assistant.db"
    form_catalog_dir: Path = Path("data/form_catalog")
    default_questionnaire_path: Path = Path("data/form_catalog/tfr_default__v0.1.json")
    batch_concurrency: int = 2

    model_config = SettingsConfigDict(extra="allow")


def get_settings() -> Settings:
    return Settings()
