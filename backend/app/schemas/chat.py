from pydantic import BaseModel, Field

from app.core.llm import LLMModelAPI, ReasoningEffort


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    active_review_id: str | None = None


class ChatResponse(BaseModel):
    message: ChatMessage


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
