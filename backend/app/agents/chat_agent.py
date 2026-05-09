from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import Agent, RunContext, ToolReturn
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai.models.test import TestModel

from app.core.config import Settings, get_settings
from app.models.chat_state import TFRChatState, log_activity


def build_chat_agent(settings: Settings | None = None) -> Agent[StateDeps[TFRChatState], str]:
    settings = settings or get_settings()
    model = (
        TestModel(
            custom_output_text=(
                "### TFR assistant is connected\n\n"
                "I received your message through the Pydantic-AI chat agent. "
                "The AG-UI endpoint is ready for CopilotKit-style streaming, shared state, "
                "and frontend tools as we wire in the real review context.\n\n"
                "| Signal | Status |\n"
                "| --- | --- |\n"
                "| Shared state | Ready |\n"
                "| Tool status | Ready |\n"
                "| Markdown tables | Visible |\n\n"
                "- Review batches can route through the worker agent.\n"
                "- Audit forms can stay structured as original and user-edited versions.\n"
                "- Evaluation findings can become prompt-optimization data."
            )
        )
        if settings.chat_model == "test"
        else settings.chat_model
    )
    return Agent(
        model,
        output_type=str,
        deps_type=StateDeps[TFRChatState],
        instructions=(
            "You are the general assistant for a Targeted File Review application. "
            "Help users navigate reviews, forms, dashboard data, and evaluation workflows. "
            "When connected to the UI, synchronize useful state through the CopilotKit AG-UI "
            "protocol rather than inventing hidden state. Use tools when you need current "
            "workspace context or need to report visible progress."
        ),
    )


chat_agent = build_chat_agent()


@chat_agent.tool
async def get_workspace_context(ctx: RunContext[StateDeps[TFRChatState]]) -> ToolReturn:
    """Summarize the currently synced TFR workspace state."""

    state = ctx.deps.state
    state.status = "using_tools"
    state.current_step = "Reading synced TFR workspace state..."
    state.progress = max(state.progress, 20)
    log_activity(state, state.current_step, "in_progress", "workspace_context")

    summary = (
        f"Active route: {state.active_route or '/'}\n"
        f"Active review ID: {state.active_review_id or 'none'}\n"
        f"Selected forms: {len(state.selected_form_ids)}\n"
        f"Documents in context: {len(state.documents)}"
    )

    state.status = "complete"
    state.current_step = "Workspace context synced."
    state.progress = 100
    log_activity(state, state.current_step, "completed", "workspace_context")
    return ToolReturn(
        return_value=summary,
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
    )
