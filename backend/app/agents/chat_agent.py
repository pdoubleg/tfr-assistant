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


CHAT_AGENT_INSTRUCTIONS = """\
You are the general assistant for a Targeted File Review (TFR) application.
Help users navigate reviews, audit forms, dashboard data, and evaluation
workflows. When connected to the UI, synchronize useful state through the
CopilotKit AG-UI protocol rather than inventing hidden state, and use tools
whenever you need current workspace context or should report visible progress.

Prefer inspection over guessing. Discover schemas, tool signatures, and form
IDs with the appropriate tools before acting, and answer from real query
results rather than assumptions.

Tool routing:
- SQL database tools: read-only analytics, table/schema inspection, selected
  homepage rows, and query-backed answers. Inspect tables and schema before
  writing SQL. Keep intermediate results as previews for your own reasoning;
  render a table only when it is clearly the answer the user asked for.
- Python repl (Monty): dataframe transforms, Plotly charts, sub-LLM text
  analysis, and output bundles. When analysis needs a chart or dataframe
  preparation, run SQL execute with persist_result=true to create a dataset
  handle, then pass that handle into the Python repl tools. Never execute SQL
  inside the repl, and never reference repl variables from SQL.
- Polished deliverables: when the user asks for a report, findings memo,
  printable analysis packet, PowerPoint deck, PPTX, briefing, or presentation,
  choose one Monty output path first: report_bundles for browser/print-friendly
  HTML reports, or deck_bundles for PowerPoint deliverables. Load only the
  chosen collection's help unless the user asks for both outputs.
- Workspace files: use the Python repl files collection for files in the
  dedicated workspace folder. Inspect directories before reading unknown
  paths, and treat Mermaid diagrams as text the frontend can render and
  download.
- One-off audit reviews: call get_registered_forms_listing first when you need
  published form IDs, then call generate_audit_form_review so the result is
  persisted and rendered for review.
- Synthetic data, smoke-style data, or completed audit intake: direct the user
  to Batch Audits instead of generating it from chat.
"""


def build_chat_agent(settings: Settings | None = None) -> Agent[TFRChatDeps, str]:
    settings = settings or get_settings()
    model = build_chat_model(settings)
    return Agent(
        model,
        output_type=str,
        deps_type=TFRChatDeps,
        retries=5,
        instructions=CHAT_AGENT_INSTRUCTIONS,
        capabilities=[SQLDatabaseCapability(), MontyPythonCapability()],
    )


chat_agent = build_chat_agent()


def _markdown_table_cell(value: object) -> str:
    text = " ".join(str(value or "").split()) or "None"
    return text.replace("|", "\\|")


def _published_forms_markdown(catalog: FormCatalog) -> str:
    definitions = [
        catalog.get_form(summary.id, summary.version)
        for summary in catalog.list_forms(published_only=True)
    ]
    if not definitions:
        return "### Published Audit Forms\n\nNo published audit forms found."

    rows = [
        "| Form ID | Version | Kind | Title | Description |",
        "| --- | --- | --- | --- | --- |",
    ]
    for definition in definitions:
        description = " ".join((definition.description or "").split()) or "None"
        rows.append(
            " | ".join(
                [
                    f"| `{_markdown_table_cell(definition.id)}`",
                    f"`{_markdown_table_cell(definition.version)}`",
                    _markdown_table_cell(definition.form_kind),
                    _markdown_table_cell(definition.title),
                    f"{_markdown_table_cell(description)} |",
                ]
            )
        )

    return "\n".join(
        [
            "### Published Audit Forms",
            "",
            (
                f"{len(definitions)} published form"
                f"{'s' if len(definitions) != 1 else ''} can be used by chat audit generation."
            ),
            "",
            *rows,
        ]
    )


@chat_agent.tool
async def get_registered_forms_listing(ctx: RunContext[TFRChatDeps]) -> ToolReturn:
    """Get published audit form IDs before calling generate_audit_form_review.

    Call this tool to get published form IDs and versions prior to running
    generate_audit_form_review so that the generation args are valid.

    Returns:
        Compact published form metadata from the form catalog.
    """

    state = ctx.deps.state
    reporter = ChatStateStatusReporter(state, source_name="get_registered_forms_listing")
    reporter.in_progress("Loading published audit forms...", progress=25)

    markdown = _published_forms_markdown(FormCatalog(ctx.deps.settings.form_catalog_dir))
    reporter.completed("Published audit forms loaded.", progress=100)
    state.status = "complete"
    state.current_step = "Published audit forms loaded."

    return ToolReturn(
        return_value=markdown,
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
    )


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

    catalog = FormCatalog(ctx.deps.settings.form_catalog_dir)
    try:
        catalog.get_published_form(form_id, form_version)
    except (KeyError, PermissionError) as exc:
        message = str(exc)
        reporter.error(message, progress=100)
        return ToolReturn(
            return_value=message,
            metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
        )

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
