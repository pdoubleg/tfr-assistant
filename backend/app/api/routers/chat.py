from fastapi import APIRouter
from pydantic_ai.ui.ag_ui import AGUIAdapter
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.agents.chat_agent import chat_agent
from app.capabilities.deps import TFRChatDeps
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
    body = await request.body()
    if not body.strip():
        return JSONResponse(
            status_code=400,
            content={
                "detail": "AG-UI endpoint requires a JSON RunAgentInput request body.",
                "hint": (
                    "Use the AG-UI HttpAgent client or POST a RunAgentInput JSON "
                    "object with threadId, runId, state, messages, tools, context, "
                    "and forwardedProps."
                ),
            },
        )

    return await AGUIAdapter.dispatch_request(
        request,
        agent=chat_agent,
        deps=TFRChatDeps(TFRChatState()),
    )
