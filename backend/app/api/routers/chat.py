import json
from collections.abc import AsyncIterator
from typing import Annotated

from ag_ui.core import BaseEvent, EventType, StateSnapshotEvent
from fastapi import APIRouter, Depends
from pydantic_ai.ui.ag_ui import AGUIAdapter
from pydantic_ai.usage import RunUsage
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.agents.chat_agent import chat_agent
from app.capabilities.deps import TFRChatDeps
from app.core.config import Settings, get_settings
from app.core.llm import (
    LLMModelAPI,
    LLMModelConfig,
    ReasoningEffort,
    available_llm_models,
    build_llm_model,
    calculate_token_cost,
    context_window_for_model,
    run_usage_to_dict,
)
from app.models.chat_state import TFRChatState
from app.schemas.chat import (
    ChatMessage,
    ChatModelCatalogResponse,
    ChatModelOption,
    ChatRequest,
    ChatResponse,
)

router = APIRouter()

MODEL_SELECTION_CONTEXT_DESCRIPTION = "TFR chat model selection"


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


@router.get("/models", response_model=ChatModelCatalogResponse)
def list_chat_models(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatModelCatalogResponse:
    default_config = settings.chat_llm_config()
    show_reasoning_effort = default_config.api == LLMModelAPI.RESPONSES
    return ChatModelCatalogResponse(
        models=[
            ChatModelOption(
                name=model.name,
                label=model.label,
                base_name=model.base_name,
                deployment_name=model.deployment_name,
                context_window=model.context_window,
                api=default_config.api,
                reasoning_efforts=model.reasoning_efforts if show_reasoning_effort else [],
                default_reasoning_effort=(
                    model.default_reasoning_effort if show_reasoning_effort else None
                ),
                default_for_chat=model.default_for_chat,
                default_for_audit=model.default_for_audit,
            )
            for model in available_llm_models(deployment_overrides=settings.llm_deployments)
        ],
        default_model_name=default_config.pricing_lookup_name,
        default_reasoning_effort=default_config.reasoning_effort if show_reasoning_effort else None,
    )


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

    settings = get_settings()
    model_name, reasoning_effort = _chat_model_selection(body)
    model_config = settings.chat_llm_config(
        model_name=model_name,
        reasoning_effort=reasoning_effort,
    )
    deps = TFRChatDeps(TFRChatState(), settings=settings)

    async def on_complete(result: object) -> AsyncIterator[BaseEvent]:
        usage = result.usage() if hasattr(result, "usage") else None
        _populate_chat_usage_state(deps.state, model_config, settings, usage)
        yield StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=deps.state)

    return await AGUIAdapter.dispatch_request(
        request,
        agent=chat_agent,
        model=build_llm_model(model_config),
        deps=deps,
        on_complete=on_complete,
    )


def _chat_model_selection(body: bytes) -> tuple[str | None, ReasoningEffort | None]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    context_items = payload.get("context")
    if not isinstance(context_items, list):
        return None, None
    for item in context_items:
        if not isinstance(item, dict):
            continue
        if item.get("description") != MODEL_SELECTION_CONTEXT_DESCRIPTION:
            continue
        value = item.get("value")
        if not isinstance(value, str):
            continue
        try:
            selection = json.loads(value)
        except json.JSONDecodeError:
            continue
        if not isinstance(selection, dict):
            continue
        model_name = selection.get("model_name")
        reasoning_effort = selection.get("reasoning_effort")
        return (
            model_name if isinstance(model_name, str) and model_name.strip() else None,
            reasoning_effort
            if reasoning_effort in {"none", "minimal", "low", "medium", "high", "xhigh"}
            else None,
        )
    return None, None


def _populate_chat_usage_state(
    state: TFRChatState,
    model_config: LLMModelConfig,
    settings: Settings,
    usage: RunUsage | None,
) -> None:
    used_tokens = int(usage.total_tokens) if usage is not None else 0
    context_window = context_window_for_model(
        model_config,
        deployment_overrides=settings.llm_deployments,
    )
    remaining_percent = None
    if context_window:
        remaining_percent = round(
            max(0.0, ((context_window - used_tokens) / context_window) * 100),
            1,
        )

    run_cost = calculate_token_cost(usage, model_config)
    state.chat_model_name = model_config.pricing_lookup_name
    state.chat_context_window = context_window
    state.chat_context_used_tokens = used_tokens
    state.chat_context_remaining_percent = remaining_percent
    state.chat_run_cost = run_cost
    state.chat_total_cost = round((state.chat_total_cost or 0.0) + run_cost, 8)
    state.chat_last_usage = run_usage_to_dict(usage)
