from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.llm import (
    DEFAULT_AUDIT_MODEL_NAME,
    DEFAULT_CHAT_MODEL_NAME,
    LLMModelAPI,
    LLMModelConfig,
    ReasoningEffort,
    ReasoningSummary,
    llm_model_config_for,
)


class Settings(BaseSettings):
    app_name: str = "Targeted File Review API"
    app_version: str = "0.1.0"
    environment: str = "local"
    llm_deployments: dict[str, str] = Field(default_factory=dict)
    chat_model: str = DEFAULT_CHAT_MODEL_NAME
    chat_model_base_name: str = ""
    chat_model_api: LLMModelAPI = LLMModelAPI.CHAT
    chat_model_reasoning_effort: ReasoningEffort | None = "low"
    chat_model_reasoning_summary: ReasoningSummary | None = "auto"
    chat_model_timeout_seconds: float = 90.0
    chat_model_send_reasoning_ids: bool = False
    audit_model: str = DEFAULT_AUDIT_MODEL_NAME
    audit_model_base_name: str = ""
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
    chat_artifacts_dir: Path = Path("data/chat_artifacts")
    optimization_runs_dir: Path = Path("data/optimization_runs")
    agent_workspace_dir: Path = Path("data/workspace")
    dataset_embedding_model_dir: Path = Path("data/models/all-MiniLM-L6-v2")
    monty_rlm_model: str = DEFAULT_AUDIT_MODEL_NAME
    monty_rlm_model_base_name: str = ""
    monty_rlm_model_api: LLMModelAPI = LLMModelAPI.CHAT
    monty_rlm_model_timeout_seconds: float | None = None
    monty_rlm_max_batch_size: int = 12
    monty_rlm_max_prompt_chars: int = 200_000
    monty_rlm_max_llm_calls: int = 50

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="allow")

    def chat_llm_config(
        self,
        *,
        model_name: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        test_output_text: str | None = None,
    ) -> LLMModelConfig:
        return llm_model_config_for(
            model_name or self.chat_model,
            api=self.chat_model_api,
            deployment_overrides=self.llm_deployments,
            base_model_name=(self.chat_model_base_name or None) if model_name is None else None,
            timeout_seconds=self.chat_model_timeout_seconds,
            reasoning_effort=reasoning_effort or self.chat_model_reasoning_effort,
            reasoning_summary=self.chat_model_reasoning_summary,
            send_reasoning_ids=self.chat_model_send_reasoning_ids,
            test_output_text=test_output_text,
        )

    def audit_llm_config(self, *, model_name: str | None = None) -> LLMModelConfig:
        return llm_model_config_for(
            model_name or self.audit_model,
            api=self.audit_model_api,
            deployment_overrides=self.llm_deployments,
            base_model_name=(self.audit_model_base_name or None) if model_name is None else None,
            timeout_seconds=self.audit_model_timeout_seconds,
        )

    def monty_rlm_llm_config(self, *, test_output_text: str | None = None) -> LLMModelConfig:
        return llm_model_config_for(
            self.monty_rlm_model or self.chat_model,
            api=self.monty_rlm_model_api,
            deployment_overrides=self.llm_deployments,
            base_model_name=self.monty_rlm_model_base_name or None,
            timeout_seconds=self.monty_rlm_model_timeout_seconds,
            test_output_text=test_output_text,
        )


def get_settings() -> Settings:
    return Settings()
