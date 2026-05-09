from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    active_review_id: str | None = None


class ChatResponse(BaseModel):
    message: ChatMessage
