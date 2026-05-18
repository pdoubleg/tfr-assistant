from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Targeted File Review API"
    app_version: str = "0.1.0"
    environment: str = "local"
    chat_model: str = Field(
        default="openai-responses:gpt-5.4-mini",
        validation_alias=AliasChoices("CHAT_MODEL", "TFR_CHAT_MODEL", "chat_model"),
    )
    chat_model_reasoning_effort: str | None = Field(
        default="low",
        validation_alias=AliasChoices(
            "CHAT_MODEL_REASONING_EFFORT",
            "TFR_CHAT_MODEL_REASONING_EFFORT",
            "chat_model_reasoning_effort",
        ),
    )
    chat_model_reasoning_summary: str | None = Field(
        default="auto",
        validation_alias=AliasChoices(
            "CHAT_MODEL_REASONING_SUMMARY",
            "TFR_CHAT_MODEL_REASONING_SUMMARY",
            "chat_model_reasoning_summary",
        ),
    )
    chat_model_timeout_seconds: float = Field(
        default=90.0,
        validation_alias=AliasChoices(
            "CHAT_MODEL_TIMEOUT_SECONDS",
            "TFR_CHAT_MODEL_TIMEOUT_SECONDS",
            "chat_model_timeout_seconds",
        ),
    )
    audit_model: str = Field(
        default="openai:gpt-5.4-nano",
        validation_alias=AliasChoices("AUDIT_MODEL", "TFR_AUDIT_MODEL", "audit_model"),
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    cors_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1):\d+$"
    data_dir: Path = Path("data")
    database_url: str = "sqlite+aiosqlite:///data/tfr_assistant.db"
    form_catalog_dir: Path = Path("data/form_catalog")
    default_questionnaire_path: Path = Path("data/form_catalog/tfr_default__v0.1.json")
    completed_intake_docs_dir: Path = Path("data/intake_docs")
    batch_concurrency: int = 2
    image_model: str = "gpt-image-2"
    generated_images_dir: Path = Path("data/generated_images")
    chat_artifacts_dir: Path = Path("data/chat_artifacts")
    agent_workspace_dir: Path = Path("data/workspace")
    monty_rlm_model: str = "openai:gpt-5.4-nano"
    monty_rlm_max_batch_size: int = 12
    monty_rlm_max_prompt_chars: int = 200_000
    monty_rlm_max_llm_calls: int = 50

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="allow")


def get_settings() -> Settings:
    return Settings()
