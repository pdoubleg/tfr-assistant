from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import Agent, RunContext, ToolReturn
from pydantic_ai.models.test import TestModel

from app.capabilities.deps import TFRChatDeps
from app.capabilities.sql import SQLDatabaseCapability
from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.schemas.reviews import ReviewGenerateRequest
from app.services.audit_generation import ChatReviewGenerationService
from app.services.status_reporter import ChatStateStatusReporter


def build_chat_agent(settings: Settings | None = None) -> Agent[TFRChatDeps, str]:
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
        deps_type=TFRChatDeps,
        instructions=(
            "You are the general assistant for a Targeted File Review application. "
            "Help users navigate reviews, forms, dashboard data, and evaluation workflows. "
            "When connected to the UI, synchronize useful state through the CopilotKit AG-UI "
            "protocol rather than inventing hidden state. Use tools when you need current "
            "workspace context or need to report visible progress. Use the SQL database tools "
            "for analytics, selected homepage rows, table/schema inspection, and query-backed "
            "answers. Generated analytics UI should be emitted as A2UI components in chat "
            "state with zone='chat'; do not target a separate output pane. When the user asks "
            "you to create, generate, run, or smoke-test an audit form review, call "
            "generate_audit_form_review so the result is persisted and rendered for review."
        ),
        capabilities=[SQLDatabaseCapability()],
    )


chat_agent = build_chat_agent()


@chat_agent.tool
async def generate_audit_form_review(
    ctx: RunContext[TFRChatDeps],
    prompt: str,
    claim_number: str = "",
    effective_date: str = "",
    form_id: str = "tfr_default",
    form_version: str = "v0.1",
    synthetic: bool = True,
) -> ToolReturn:
    """Spawn a sub-agent to generate an AuditFormResult review.

    Use synthetic=True for quick examples and smoke tests not involving the sub-agent. Use
    synthetic=False to employ the sub-agent.
    """

    state = ctx.deps.state
    reporter = ChatStateStatusReporter(state)
    reporter.in_progress("Starting audit form generation tool...", progress=10)

    request = ReviewGenerateRequest(
        prompt=prompt,
        claim_number=claim_number,
        effective_date=effective_date,
        instructions=prompt,
        form_id=form_id,
        form_version=form_version,
        synthetic=synthetic,
    )
    async with AsyncSessionLocal() as session:
        review = await ChatReviewGenerationService(session).generate(
            request,
            reporter=reporter,
        )

    state.active_review_id = review.id
    if review.status == "completed":
        state.status = "complete"
        state.current_step = f"Audit review {review.id} is ready."
    else:
        state.status = "error"
        state.error_message = review.error_message
        state.current_step = f"Audit review {review.id} failed."

    output = (
        f"Audit review {review.id} saved with status {review.status}.\n"
        f"Form: {review.form_id}@{review.form_version}\n"
        f"Active review ID: {review.id}"
        f"Results: {str(review.original)}"
    )
    return ToolReturn(
        return_value=output,
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
    )
