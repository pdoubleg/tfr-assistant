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
    """Application settings loaded from the environment and .env files."""

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_name: str = "Targeted File Review API"
    """Human-readable API name surfaced in docs and health endpoints."""

    app_version: str = "0.1.0"
    """Application version string."""

    environment: str = "local"
    """Deployment environment label (e.g. "local", "dev", "prod")."""

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    """Explicit origins allowed to call the API."""

    cors_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1):\d+$"
    """Regex of additional allowed origins; None disables regex matching."""

    # ------------------------------------------------------------------
    # Storage and data paths
    # ------------------------------------------------------------------
    data_dir: Path = Path("data")
    """Root directory for all on-disk application data."""

    database_url: str = "sqlite+aiosqlite:///data/tfr_assistant.db"
    """SQLAlchemy database URL for the primary application database."""

    form_catalog_dir: Path = Path("data/form_catalog")
    """Directory holding versioned form/questionnaire catalog JSON files."""

    default_questionnaire_path: Path = Path("data/form_catalog/tfr_default__v0.1.json")
    """Catalog entry used when no questionnaire is specified."""

    completed_intake_docs_dir: Path = Path("data/intake_docs")
    """Directory where completed intake documents are written."""

    chat_artifacts_dir: Path = Path("data/chat_artifacts")
    """Per-session datasets, charts, and bundles created by chat tools."""

    optimization_runs_dir: Path = Path("data/optimization_runs")
    """Artifacts and logs produced by prompt optimization runs."""

    agent_workspace_dir: Path = Path("data/workspace")
    """Scratch workspace the chat agent can read files from."""

    dataset_embedding_model_dir: Path = Path("data/models/all-MiniLM-L6-v2")
    """Local path of the sentence-embedding model used for dataset search."""

    # ------------------------------------------------------------------
    # Background processing
    # ------------------------------------------------------------------
    batch_concurrency: int = 2
    """Maximum concurrent audit jobs processed per batch."""

    # ------------------------------------------------------------------
    # LLM routing
    # ------------------------------------------------------------------
    llm_deployments: dict[str, str] = Field(default_factory=dict)
    """Optional model-name -> deployment-name overrides for hosted LLMs."""

    # ------------------------------------------------------------------
    # Chat model (primary chat agent)
    # ------------------------------------------------------------------
    chat_model: str = DEFAULT_CHAT_MODEL_NAME
    """Model name used by the chat agent."""

    chat_model_base_name: str = ""
    """Base model name override when chat_model is a deployment alias."""

    chat_model_api: LLMModelAPI = LLMModelAPI.CHAT
    """API flavor used to call the chat model."""

    chat_model_reasoning_effort: ReasoningEffort | None = "low"
    """Default reasoning effort for the chat model, when supported."""

    chat_model_reasoning_summary: ReasoningSummary | None = "auto"
    """Reasoning summary verbosity for the chat model, when supported."""

    chat_model_timeout_seconds: float = 90.0
    """Per-request timeout for chat model calls."""

    chat_model_send_reasoning_ids: bool = False
    """Whether to send reasoning item IDs back to the chat model."""

    # ------------------------------------------------------------------
    # Audit model (form auditing pipeline)
    # ------------------------------------------------------------------
    audit_model: str = DEFAULT_AUDIT_MODEL_NAME
    """Model name used by the audit pipeline."""

    audit_model_base_name: str = ""
    """Base model name override when audit_model is a deployment alias."""

    audit_model_api: LLMModelAPI = LLMModelAPI.CHAT
    """API flavor used to call the audit model."""

    audit_model_timeout_seconds: float | None = None
    """Per-request timeout for audit model calls; None uses the client default."""

    # ------------------------------------------------------------------
    # Monty sub-LLM (RLM tools in the Python repl)
    # ------------------------------------------------------------------
    monty_rlm_model: str = DEFAULT_AUDIT_MODEL_NAME
    """Model name used for sub-LLM queries issued from the Python repl."""

    monty_rlm_model_base_name: str = ""
    """Base model name override when monty_rlm_model is a deployment alias."""

    monty_rlm_model_api: LLMModelAPI = LLMModelAPI.CHAT
    """API flavor used to call the sub-LLM."""

    monty_rlm_model_timeout_seconds: float | None = None
    """Per-request timeout for sub-LLM calls; None uses the client default."""

    monty_rlm_max_batch_size: int = 12
    """Maximum prompts accepted by one llm_query_batched() call."""

    monty_rlm_max_prompt_chars: int = 200_000
    """Maximum characters allowed in a single sub-LLM prompt."""

    monty_rlm_max_llm_calls: int = 50
    """Total sub-LLM call budget per artifact session."""

    monty_rlm_chunk_max_chars: int = 20_000
    """Default max_chars for dataset_chunks() when the caller omits it."""

    monty_rlm_prompt_headroom_chars: int = 2_000
    """Headroom kept under the prompt limit so chunked prompts always leave
    room for the caller's task instructions; chunk sizes are clamped to
    monty_rlm_max_prompt_chars minus this value."""

    monty_rlm_meta_value_max_chars: int = 200
    """Cap on each metadata value rendered into dataset_chunks() record
    headers, so a noisy column cannot crowd out record text."""

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
