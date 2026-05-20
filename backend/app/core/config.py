from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.llm import LLMModelAPI, LLMModelConfig, ReasoningEffort, ReasoningSummary


class Settings(BaseSettings):
    app_name: str = "Targeted File Review API"
    app_version: str = "0.1.0"
    environment: str = "local"
    chat_model: str = "gpt-5.4-mini"
    chat_model_api: LLMModelAPI = LLMModelAPI.RESPONSES
    chat_model_reasoning_effort: ReasoningEffort | None = "low"
    chat_model_reasoning_summary: ReasoningSummary | None = "auto"
    chat_model_timeout_seconds: float = 90.0
    chat_model_send_reasoning_ids: bool = False
    audit_model: str = "gpt-5.4-nano"
    audit_model_api: LLMModelAPI = LLMModelAPI.CHAT
    audit_model_timeout_seconds: float | None = None
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
    optimization_runs_dir: Path = Path("data/optimization_runs")
    agent_workspace_dir: Path = Path("data/workspace")
    monty_rlm_model: str = "gpt-5.4-nano"
    monty_rlm_model_api: LLMModelAPI = LLMModelAPI.CHAT
    monty_rlm_model_timeout_seconds: float | None = None
    monty_rlm_max_batch_size: int = 12
    monty_rlm_max_prompt_chars: int = 200_000
    monty_rlm_max_llm_calls: int = 50

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="allow")

    def chat_llm_config(self, *, test_output_text: str | None = None) -> LLMModelConfig:
        return LLMModelConfig(
            model_name=self.chat_model,
            api=self.chat_model_api,
            timeout_seconds=self.chat_model_timeout_seconds,
            reasoning_effort=self.chat_model_reasoning_effort,
            reasoning_summary=self.chat_model_reasoning_summary,
            send_reasoning_ids=self.chat_model_send_reasoning_ids,
            test_output_text=test_output_text,
        )

    def audit_llm_config(self) -> LLMModelConfig:
        return LLMModelConfig(
            model_name=self.audit_model,
            api=self.audit_model_api,
            timeout_seconds=self.audit_model_timeout_seconds,
        )

    def monty_rlm_llm_config(self, *, test_output_text: str | None = None) -> LLMModelConfig:
        return LLMModelConfig(
            model_name=self.monty_rlm_model or self.chat_model,
            api=self.monty_rlm_model_api,
            timeout_seconds=self.monty_rlm_model_timeout_seconds,
            test_output_text=test_output_text,
        )


def get_settings() -> Settings:
    return Settings()
