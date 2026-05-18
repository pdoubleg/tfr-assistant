import json

from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import Agent, RunContext, ToolReturn
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings

from app.capabilities.deps import TFRChatDeps
from app.capabilities.monty import MontyPythonCapability
from app.capabilities.sql import SQLDatabaseCapability
from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.presenters.a2ui import generate_image_card
from app.schemas.reviews import ReviewGenerateRequest
from app.services.audit_generation import ChatReviewGenerationService
from app.services.image_generation import (
    ImageBackground,
    ImageFormat,
    ImageGenerationError,
    ImageGenerationService,
    ImageQuality,
)
from app.services.status_reporter import ChatStateStatusReporter


def build_chat_model(settings: Settings) -> str | OpenAIResponsesModel | TestModel:
    model_name = settings.chat_model.strip()
    if model_name == "test":
        return TestModel(
            custom_output_text=(
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
        )

    if model_name.startswith("openai-responses:"):
        responses_model_name = model_name.removeprefix("openai-responses:").strip()
        model_settings: ModelSettings = {
            "timeout": settings.chat_model_timeout_seconds,
            # AG-UI reconstructs prior messages from frontend state. Do not send
            # Responses item IDs unless the exact provider history is preserved.
            "openai_send_reasoning_ids": False,
        }
        if settings.chat_model_reasoning_effort:
            model_settings["openai_reasoning_effort"] = settings.chat_model_reasoning_effort
        if settings.chat_model_reasoning_summary:
            model_settings["openai_reasoning_summary"] = settings.chat_model_reasoning_summary
        return OpenAIResponsesModel(responses_model_name, settings=model_settings)

    return model_name


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
            "Do not execute SQL inside the Python repl. When the user asks "
            "for an image, illustration, visual concept, mockup, or other generated picture, "
            "call generate_image and let the tool persist and render the image in chat. "
            "Do not respond with an external image URL instead of using the tool. "
            "Use the Python repl files collection for files in the dedicated workspace "
            "folder; inspect directories before reading unknown paths, and treat Mermaid "
            "diagrams as text that the frontend can render and download. "
            "When the user asks you to create or generate a one-off audit form review, call "
            "generate_audit_form_review so the result is persisted and rendered for review. "
            "For synthetic data, smoke-style data, or completed audit intake, direct the user "
            "to Batch Audits instead of generating it from chat."
        ),
        capabilities=[SQLDatabaseCapability(), MontyPythonCapability()],
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
) -> ToolReturn:
    """Spawn a sub-agent to generate one AuditFormResult review."""

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
        synthetic=False,
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


@chat_agent.tool
async def generate_image(
    ctx: RunContext[TFRChatDeps],
    prompt: str,
    size: str = "1536x864",
    quality: ImageQuality = "high",
    n: int = 1,
    output_format: ImageFormat = "png",
    background: ImageBackground = "auto",
) -> ToolReturn:
    """Generate image artifacts and render them in the chat UI.

    Use this whenever the user asks for an image, illustration, mockup, scene,
    or other AI-generated visual. The tool saves generated files in the backend
    data directory and emits chat components that the frontend can render.
    """

    state = ctx.deps.state
    reporter = ChatStateStatusReporter(state, source_name="image_generation")
    reporter.in_progress("Generating image with OpenAI...", progress=20)

    try:
        images = await ImageGenerationService(ctx.deps.settings).generate(
            prompt=prompt,
            size=size,
            quality=quality,
            n=n,
            output_format=output_format,
            background=background,
        )
    except ImageGenerationError as exc:
        reporter.error(f"Image generation failed: {exc}", progress=100)
        return ToolReturn(
            return_value=f"Unable to generate image: {exc}",
            metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
        )

    for image in images:
        state.components.append(generate_image_card(image))

    reporter.completed(
        f"Generated {len(images)} image{'s' if len(images) != 1 else ''}.",
        progress=100,
    )
    state.status = "complete"

    payload = [
        {
            "url": image.url,
            "filename": image.filename,
            "model": image.model,
            "size": image.size,
            "quality": image.quality,
            "mime_type": image.mime_type,
        }
        for image in images
    ]
    return ToolReturn(
        return_value=(
            "Generated image artifact(s) saved and emitted to the chat UI.\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        ),
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
    )
