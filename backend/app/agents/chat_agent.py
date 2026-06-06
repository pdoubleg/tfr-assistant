from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import Agent, RunContext, ToolReturn
from pydantic_ai.models import Model

from app.capabilities.deps import TFRChatDeps
from app.capabilities.monty import MontyPythonCapability
from app.capabilities.sql import SQLDatabaseCapability
from app.core.config import Settings, get_settings
from app.core.llm import build_llm_model
from app.db.session import AsyncSessionLocal
from app.presenters.a2ui import generate_audit_review_card
from app.schemas.reviews import ReviewGenerateRequest
from app.services.audit_generation import ChatReviewGenerationService
from app.services.catalog import FormCatalog
from app.services.status_reporter import ChatStateStatusReporter

CHAT_TEST_OUTPUT = (
    "### TFR assistant is connected\n\n"
    "I received your message through the Pydantic-AI chat agent. "
    "The AG-UI endpoint is ready for CopilotKit-style streaming, shared state, "
    "and frontend tools as we wire in the real review context.\n\n"
    "| Signal | Status |\n"
    "| --- | --- |\n"
    "| Shared state | Ready |\n"
    "| Tool status | Ready |\n\n"
    "- Review batches can route through the worker agent.\n"
    "- Audit forms can stay structured as original and user-edited versions.\n"
    "- Evaluation findings can become prompt-optimization data."
)


def build_chat_model(settings: Settings) -> Model[object]:
    return build_llm_model(settings.chat_llm_config(test_output_text=CHAT_TEST_OUTPUT))


def build_chat_agent(settings: Settings | None = None) -> Agent[TFRChatDeps, str]:
    settings = settings or get_settings()
    model = build_chat_model(settings)
    return Agent(
        model,
        output_type=str,
        deps_type=TFRChatDeps,
        retries=5,
        instructions=(
            "You are the general assistant for a Targeted File Review application. "
            "Help users navigate reviews, forms, dashboard data, and evaluation workflows. "
            "When connected to the UI, synchronize useful state through the CopilotKit AG-UI "
            "protocol rather than inventing hidden state. Use tools when you need current "
            "workspace context or need to report visible progress. Use the SQL database tools "
            "for analytics, selected homepage rows, table/schema inspection, and query-backed "
            "answers. Generated analytics UI should be emitted as A2UI components in chat "
            "state with zone='chat'; do not target a separate output pane. When the user asks "
            "for analysis that needs a chart or Python dataframe preparation, use SQL execute "
            "with persist_result=true to create a dataset handle, then use the Python repl "
            "tools to transform the handle and emit Plotly charts or tables. "
            "When the user asks for a polished report, findings memo, printable "
            "analysis packet, PowerPoint deck, PPTX, briefing, or presentation, choose "
            "one Monty output path first: report_bundles for browser/print-friendly HTML "
            "reports, or deck_bundles for PowerPoint deliverables. Load only the chosen "
            "collection help unless the user asks for both outputs. "
            "Do not execute SQL inside the Python repl. When the user asks "
            "for image generation, explain that generated images are no longer supported. "
            "Use the Python repl files collection for files in the dedicated workspace "
            "folder; inspect directories before reading unknown paths, and treat Mermaid "
            "diagrams as text that the frontend can render and download. "
            "When the user asks you to create or generate a one-off audit form review, call "
            "get_registered_forms_listing first when you need valid form IDs, then call "
            "generate_audit_form_review so the result is persisted and rendered for review. "
            "For synthetic data, smoke-style data, or completed audit intake, direct the user "
            "to Batch Audits instead of generating it from chat."
        ),
        capabilities=[SQLDatabaseCapability(), MontyPythonCapability()],
    )


chat_agent = build_chat_agent()


@chat_agent.tool
async def get_registered_forms_listing(ctx: RunContext[TFRChatDeps]) -> str:
    """Get valid audit form IDs before calling generate_audit_form_review.

    Call this tool to get valid form IDs and versions prior to running
    generate_audit_form_review so that the generation args are valid.

    Returns:
        Compact registered form metadata from the form catalog.
    """

    catalog = FormCatalog(ctx.deps.settings.form_catalog_dir)
    definitions = [
        catalog.get_form(summary.id, summary.version) for summary in catalog.list_forms()
    ]
    if not definitions:
        return "No registered audit forms found."
    lines = ["Registered audit forms:"]
    for definition in definitions:
        description = " ".join((definition.description or "").split()) or "None"
        lines.append(
            "; ".join(
                [
                    f"canonical_form_id={definition.canonical.form_id}",
                    f"form_kind={definition.form_kind}",
                    f"form_id={definition.id}",
                    f"form_version={definition.version}",
                    f"title={definition.title}",
                    f"description={description}",
                ]
            )
        )
    return "\n".join(lines)


@chat_agent.tool
async def generate_audit_form_review(
    ctx: RunContext[TFRChatDeps],
    claim_number: str,
    form_id: str,
    effective_date: str = "",
    form_version: str = "v0.1",
) -> ToolReturn:
    """Spawn a sub-agent to generate one AuditFormResult review.

    Args:
        claim_number: The claim number to generate a review for.
        form_id: The form ID to generate a review for.
        effective_date: The effective date to generate a review for.
        form_version: The form version to generate a review for.

    Returns:
        A tool return with the form result and generated component.
    """

    state = ctx.deps.state
    reporter = ChatStateStatusReporter(state)
    reporter.in_progress("Starting audit form generation tool...", progress=10)

    request = ReviewGenerateRequest(
        claim_number=claim_number,
        effective_date=effective_date,
        form_id=form_id,
        form_version=form_version,
        synthetic=False,
    )
    async with AsyncSessionLocal() as session:
        review = await ChatReviewGenerationService(session).generate(
            request,
            reporter=reporter,
        )

    state.active_review_id = review.id
    if review.status == "completed":
        component = generate_audit_review_card(review)
        if component is not None:
            state.components = [
                existing for existing in state.components if existing.id != component.id
            ]
            state.components.append(component)
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
