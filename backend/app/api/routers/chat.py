from fastapi import APIRouter

from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    last_user_message = next(
        (message.content for message in reversed(request.messages) if message.role == "user"),
        "",
    )
    content = (
        "Chat agent scaffold is ready. CopilotKit AG-UI wiring will attach here. "
        f"Last user message: {last_user_message}"
    )
    return ChatResponse(message=ChatMessage(role="assistant", content=content))

