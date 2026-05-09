from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Targeted File Review API"
    app_version: str = "0.1.0"
    environment: str = "local"
    chat_model: str = "openai:gpt-5.4-nano"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    data_dir: Path = Path("data")
    form_catalog_dir: Path = Path("data/form_catalog")

    model_config = SettingsConfigDict(extra="allow")


def get_settings() -> Settings:
    return Settings()
