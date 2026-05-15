from fastapi import APIRouter
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.requests import Request
from starlette.responses import Response

from app.agents.chat_agent import chat_agent
from app.models.chat_state import TFRChatState
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


@router.post("/ag-ui")
async def chat_ag_ui(request: Request) -> Response:
    return await AGUIAdapter.dispatch_request(
        request,
        agent=chat_agent,
        deps=StateDeps(TFRChatState()),
    )
