from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Targeted File Review API"
    app_version: str = "0.1.0"
    environment: str = "local"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    data_dir: Path = Path("data")
    form_catalog_dir: Path = Path("data/form_catalog")

    model_config = SettingsConfigDict(env_prefix="TFR_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()

