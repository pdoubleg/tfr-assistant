from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import Agent, RunContext, ToolReturn
from pydantic_ai.ag_ui import StateDeps
from pydantic_ai.models.test import TestModel

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.models.chat_state import TFRChatState
from app.presenters.a2ui import generate_data_table
from app.schemas.reviews import ReviewGenerateRequest
from app.services.audit_generation import ChatReviewGenerationService
from app.services.status_reporter import ChatStateStatusReporter


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
            "workspace context or need to report visible progress. When the user asks you to "
            "inspect selected forms, selected rows, current table selections, or analytics scoped "
            "to the selected home-page reviews, first call summarize_selected_home_rows. "
            "Generated analytics UI should be emitted as A2UI components in chat state with "
            "zone='chat'; do not target a separate output pane. When the user asks you to "
            "create, generate, run, or smoke-test an audit form review, call "
            "generate_audit_form_review so the result is persisted and rendered for review."
        ),
    )


chat_agent = build_chat_agent()


@chat_agent.tool
async def summarize_selected_home_rows(ctx: RunContext[StateDeps[TFRChatState]]) -> ToolReturn:
    """Summarize the home page audit rows selected by the user at run time."""

    state = ctx.deps.state
    reporter = ChatStateStatusReporter(state, source_name="home_table_selection")
    reporter.in_progress("Reading selected home table rows...", progress=25)

    selected_rows = list(state.run_context.selected_home_rows) if state.run_context else []
    if not selected_rows:
        reporter.completed("No home table rows are selected.", progress=100)
        state.status = "complete"
        state.progress = 100
        state.current_step = "No home table rows are selected."
        return ToolReturn(
            return_value=(
                "No home table rows are selected in the run context. Ask the user to select rows "
                "in the home page audit table before running selection-scoped analysis."
            ),
            metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
        )

    state.selected_form_ids = sorted({row.form_key for row in selected_rows if row.form_key})
    state.active_review_id = selected_rows[0].review_id

    table_rows = [
        [
            row.claim_number or row.review_id[:8],
            row.form_key,
            row.outcome,
            row.source or "api",
            row.question_count,
            row.no_count,
            row.driver_count,
            "Yes" if row.edited else "No",
            row.review_id[:8],
        ]
        for row in selected_rows
    ]
    component = generate_data_table(
        headers=[
            "Claim",
            "Form",
            "Outcome",
            "Source",
            "Questions",
            "No",
            "Drivers",
            "Edited",
            "Review",
        ],
        rows=table_rows,
        caption=f"Selected audit rows ({len(selected_rows)})",
        sortable=True,
    )
    state.components.append(component)
    reporter.completed(f"Loaded {len(selected_rows)} selected home table rows.", progress=100)
    state.status = "complete"
    state.current_step = f"{len(selected_rows)} selected home table rows are available."

    return ToolReturn(
        return_value=(
            f"{len(selected_rows)} home table row(s) are selected. The selection includes "
            f"{len(state.selected_form_ids)} distinct form(s): "
            f"{', '.join(state.selected_form_ids) if state.selected_form_ids else 'none'}."
        ),
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
    )


@chat_agent.tool
async def generate_audit_form_review(
    ctx: RunContext[StateDeps[TFRChatState]],
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
