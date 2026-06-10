from pydantic import BaseModel, Field

from app.core.llm import LLMModelAPI, ReasoningEffort


class ChatModelOption(BaseModel):
    name: str
    label: str
    base_name: str
    deployment_name: str
    context_window: int | None = None
    api: LLMModelAPI
    reasoning_efforts: list[ReasoningEffort] = Field(default_factory=list)
    default_reasoning_effort: ReasoningEffort | None = None
    default_for_chat: bool = False
    default_for_audit: bool = False


class ChatModelCatalogResponse(BaseModel):
    models: list[ChatModelOption]
    default_model_name: str
    default_reasoning_effort: ReasoningEffort | None = None


class ChatThreadSummary(BaseModel):
    id: str
    title: str
    model_name: str = ""
    reasoning_effort: ReasoningEffort | None = None
    artifact_session_id: str = ""
    token_usage: dict[str, int] = Field(default_factory=dict)
    context_window: int | None = None
    context_used_tokens: int = 0
    context_remaining_percent: float | None = None
    run_cost: float = 0.0
    total_cost: float = 0.0
    created_at: str
    updated_at: str


class ChatThreadRecord(ChatThreadSummary):
    messages: list[dict] = Field(default_factory=list)
    state: dict = Field(default_factory=dict)
    component_anchor_turns: dict[str, int] = Field(default_factory=dict)
