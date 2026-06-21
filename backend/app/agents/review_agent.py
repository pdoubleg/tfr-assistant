import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, ToolDefinition
from pydantic_ai.capabilities import AgentCapability, PrepareTools

from app.agents.tools.policy_summary import (
    async_build_policy_summary_report,
    discover_workspace_pdf_paths,
    resolve_workspace_dir,
)
from app.core.config import Settings, get_settings
from app.core.llm import LLMModelConfig, LLMRunCostTracker, build_llm_model
from app.models.audit import (
    AuditFormResult,
    AuditFormWithFinancialsResult,
    AuditResult,
    parse_audit_result,
)
from app.schemas.forms import (
    ALL_REVIEW_AGENT_TOOLS,
    AuditFormDefinition,
    ReviewAgentToolName,
    normalize_review_agent_tool_names,
)

settings = get_settings()
logger = logging.getLogger(__name__)


DEFAULT_REVIEW_INSTRUCTIONS = (
    "You are a file review worker. Your only job is to complete audit form "
    "questionnaires from file evidence. Use the registered audit form and runtime "
    "context provided in the additional instructions to guide your focus and output.\n"
    "When policy-summary extraction is enabled and policy terms matter to the review, "
    "call get_policy_summary_extract with an effective_date and optional focus_area.\n"
    "If user requests an example audit, create a fictitious result as a demonstration.\n"
    "Output must validate exactly as the registered audit form result schema. Use only "
    "Yes or No for question answers. If the canonical standard question lists "
    "sub_questions, return only the listed sub_question driver(s) that apply, with "
    "reasoning and citations on each one. Financial audit forms are flat and require "
    "total_amount_reviewed_dollars plus question-level overwrite_dollars and "
    "underwrite_dollars."
)

REVIEW_USER_PROMPT = "Please run a TFR review"

SYNTHETIC_REVIEW_INSTRUCTIONS = (
    "You are generating synthetic completed audit form data for development, testing, "
    "and evaluation. The audit form is provided below. Create a plausible fictitious "
    "claim scenario and complete every canonical question. Follow the user's requested "
    "scenario, rating pattern, or issue mix when provided. Do not reference real people "
    "or real claim files. Output must validate exactly as the registered audit form result schema."
)

COMPLETED_INTAKE_INSTRUCTIONS = (
    "You are transferring an already-completed audit form from a provided document into "
    "structured data. The canonical form is provided below. Faithfully copy the completed "
    "answers, comments, reasoning, citations, outcome, and any available claim metadata "
    "from the document into the output. Use best effort when the document clearly appears "
    "to be a related completed audit for this form. Return AuditIntakeFailure only when "
    "the document is clearly unrelated, empty/unreadable, for the wrong form, or otherwise "
    "not a completed audit. Do not invent claim metadata; put unknown metadata keys in "
    "form_metadata only when the document supports them."
)


class CompletedAuditIntakeResult(BaseModel):
    claim_number: str = Field(
        default="",
        description="Claim number extracted from the completed audit document.",
    )
    form_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Additional metadata copied from the document, such as reviewer or audit date.",
    )
    result: AuditFormResult


class CompletedFinancialAuditIntakeResult(BaseModel):
    claim_number: str = Field(
        default="",
        description="Claim number extracted from the completed audit document.",
    )
    form_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Additional metadata copied from the document, such as reviewer or audit date.",
    )
    result: AuditFormWithFinancialsResult


class AuditIntakeFailure(BaseModel):
    reason: str
    details: str = ""


@dataclass
class FileReviewAgentDeps:
    path_to_questionnaire: str = ""
    claim_number: str = ""
    effective_date: str = ""
    runtime_context: str = ""
    tools: list[str | ReviewAgentToolName] | None = None
    knowledge_docs: list[str] | None = None
    include_state_compliance: bool | None = None
    cost_tracker: LLMRunCostTracker = field(default_factory=LLMRunCostTracker)
    form_path: Path = field(init=False)
    form_definition: AuditFormDefinition = field(init=False)
    canonical: AuditResult = field(init=False)

    def __post_init__(self) -> None:
        self.form_path = Path(self.path_to_questionnaire or settings.default_questionnaire_path)
        self.form_definition = load_form_definition(self.form_path)
        self.canonical = self.form_definition.canonical
        if self.tools is None:
            self.tools = list(self.form_definition.tools or [])
        else:
            self.tools = list(normalize_review_agent_tool_names(self.tools) or [])
        if self.knowledge_docs is None:
            self.knowledge_docs = list(self.form_definition.knowledge_docs or [])
        if self.include_state_compliance is None:
            self.include_state_compliance = self.form_definition.include_state_compliance


_ALL_REVIEW_AGENT_TOOL_NAMES = {tool.value for tool in ALL_REVIEW_AGENT_TOOLS}


def _enabled_review_tool_names(tools: list[str | ReviewAgentToolName] | None) -> set[str]:
    normalized = normalize_review_agent_tool_names(tools or []) or []
    return {
        tool.value if isinstance(tool, ReviewAgentToolName) else str(tool) for tool in normalized
    }


async def _prepare_review_agent_tools(
    ctx: RunContext[FileReviewAgentDeps],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition] | None:
    enabled_tool_names = _enabled_review_tool_names(ctx.deps.tools)
    return [
        tool_def
        for tool_def in tool_defs
        if tool_def.name not in _ALL_REVIEW_AGENT_TOOL_NAMES or tool_def.name in enabled_tool_names
    ]


def load_canonical_form(path: str | Path) -> AuditResult:
    source = Path(path)
    payload = source.read_text(encoding="utf-8")
    try:
        return AuditFormDefinition.model_validate_json(payload).canonical
    except Exception:
        return parse_audit_result(json.loads(payload))


def load_form_definition(path: str | Path) -> AuditFormDefinition:
    source = Path(path)
    payload = source.read_text(encoding="utf-8")
    try:
        return AuditFormDefinition.model_validate_json(payload)
    except Exception:
        canonical = parse_audit_result(json.loads(payload))
        return AuditFormDefinition(
            id=canonical.form_id,
            version=canonical.form_version,
            title=canonical.title,
            form_kind=canonical.form_kind,
            description=canonical.description,
            canonical=canonical,
        )


def build_file_review_agent(
    active_settings: Settings | None = None,
    *,
    model_config: LLMModelConfig | None = None,
    model_name: str | None = None,
) -> Agent[FileReviewAgentDeps, AuditFormResult]:
    active_settings = active_settings or settings
    model_config = model_config or active_settings.audit_llm_config(model_name=model_name)
    agent = Agent(
        build_llm_model(model_config),
        output_type=AuditFormResult,
        deps_type=FileReviewAgentDeps,
        validation_context=lambda ctx: ctx.deps,
        retries=3,
        output_retries=3,
        instructions=DEFAULT_REVIEW_INSTRUCTIONS,
        capabilities=[PrepareTools(_prepare_review_agent_tools)],
    )

    @agent.instructions
    def add_tfr_template(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Add the TFR template to the instructions."""
        return ctx.deps.form_definition.canonical.as_questionnaire_string()

    @agent.instructions
    def add_runtime_context(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Add per-run claim/review context."""
        sections: list[str] = []
        if ctx.deps.claim_number:
            sections.extend(["Claim Number:", ctx.deps.claim_number])
        if ctx.deps.effective_date:
            if sections:
                sections.append("")
            sections.extend(["Effective Date:", ctx.deps.effective_date])
        if ctx.deps.runtime_context:
            if sections:
                sections.append("")
            sections.extend(["Review Input:", ctx.deps.runtime_context])
        return "\n".join(sections)

    @agent.instructions
    def add_knowledge_documents(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Add the knowledge documents to the instructions."""
        parts: list[str] = []
        doc_ids = ctx.deps.knowledge_docs
        if doc_ids:
            parts.append("Knowledge Documents:\n" + "\n".join(f"- {doc}" for doc in doc_ids))

        if ctx.deps.include_state_compliance:
            parts.append("State Compliance Documents: [State Compliance Documents]")

        return "\n\n".join(parts)

    @agent.tool
    async def get_claim_summary(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Placeholder tool to get a summary of the claim."""
        return "Claim summary"

    @agent.tool
    async def get_claim_notes(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Placeholder tool to get the notes for the claim."""
        return "Claim notes"

    @agent.tool
    async def get_claim_documents_metadata(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Placeholder tool to get the metadata for the documents for the claim."""
        return "Claim documents metadata"

    @agent.tool
    async def get_claim_document_content(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Placeholder tool to get the documents for the claim."""
        return "Claim document content"

    @agent.tool
    async def get_policy_documents_metadata(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Placeholder tool to get the metadata for the documents for the policy."""
        return "Policy documents metadata"

    @agent.tool
    async def get_policy_document_content(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Placeholder tool to get the documents for the policy."""
        return "Policy document content"

    @agent.tool
    async def get_policy_summary_extract(
        ctx: RunContext[FileReviewAgentDeps],
        effective_date: str,
        focus_area: str = "",
    ) -> str:
        """Build a policy summary extract from policy PDFs in the workspace.

        Args:
            effective_date: Policy as-of or effective date, preferably YYYY-MM-DD.
            focus_area: Optional claim, peril, coverage, or audit focus area.
        """

        pdf_paths = discover_workspace_pdf_paths(active_settings.agent_workspace_dir)
        if not pdf_paths:
            workspace_dir = resolve_workspace_dir(active_settings.agent_workspace_dir)
            return f"No policy PDFs found in workspace directory: {workspace_dir}"

        requested_date = effective_date.strip() or ctx.deps.effective_date
        return await async_build_policy_summary_report(
            pdf_paths,
            effective_date=requested_date,
            focus_area=focus_area,
            model_config=active_settings.policy_summary_extraction_llm_config(),
            filter_model_config=active_settings.policy_summary_filter_llm_config(),
            synthesis_model_config=active_settings.policy_summary_synthesis_llm_config(),
            cost_tracker=ctx.deps.cost_tracker,
        )

    @agent.tool
    async def get_image_analysis(ctx: RunContext[FileReviewAgentDeps]) -> str:
        """Placeholder tool to get the analysis of the images for the claim."""
        return "Image analysis"

    return agent


def _instruction_callables(agent: Agent[FileReviewAgentDeps, AuditFormResult]) -> tuple[Any, ...]:
    instructions = getattr(agent, "_instructions", ())
    return tuple(part for part in instructions if not isinstance(part, str) and callable(part))


def _mode_instructions(
    agent: Agent[FileReviewAgentDeps, AuditFormResult],
    mode_prompt: str,
) -> tuple[Any, ...]:
    return (mode_prompt, *_instruction_callables(agent))


def _exception_chain(exc: BaseException) -> list[str]:
    chain: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return chain


def _model_label(model: object) -> str:
    if isinstance(model, LLMModelConfig):
        return model.label
    if isinstance(model, str):
        return model
    model_name = getattr(model, "model_name", None)
    if isinstance(model_name, str) and model_name:
        return f"{type(model).__name__}({model_name})"
    return type(model).__name__


def _truncate(value: object, limit: int = 1200) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _agent_failure_message(
    exc: Exception,
    *,
    deps: FileReviewAgentDeps,
    prompt: str,
    model_config: LLMModelConfig,
) -> str:
    lines = [
        "File review agent failed.",
        f"Model: {_model_label(model_config)}",
        f"Questionnaire: {deps.form_definition.id}@{deps.form_definition.version}",
        f"Questionnaire path: {deps.form_path}",
        f"Prompt preview: {_truncate(prompt, 800)}",
        "Exception chain:",
    ]
    lines.extend(f"- {_truncate(entry)}" for entry in _exception_chain(exc))
    return "\n".join(lines)


def _populate_runtime_metadata(
    output: AuditResult,
    *,
    deps: FileReviewAgentDeps,
    usage: Any,
    model_config: LLMModelConfig,
    source: str,
    started_at: float,
) -> None:
    deps.cost_tracker.add_usage(usage, model_config, source=source)
    output.cost = deps.cost_tracker.total_cost
    output.latency = round(max(time.perf_counter() - started_at, 0.0), 4)


async def run_file_review_agent(
    claim_number: str,
    effective_date: str,
    path_to_questionnaire: str = "",
    runtime_context: str = "",
    tools: list[str] | None = None,
    knowledge_docs: list[str] | None = None,
    system_prompt: str | None = None,
    capabilities: Sequence[AgentCapability[FileReviewAgentDeps]] | None = None,
    active_settings: Settings | None = None,
    model_name: str | None = None,
) -> AuditResult:
    active_settings = active_settings or settings
    model_config = active_settings.audit_llm_config(model_name=model_name)
    agent = build_file_review_agent(active_settings, model_config=model_config)
    deps = FileReviewAgentDeps(
        path_to_questionnaire=path_to_questionnaire,
        claim_number=claim_number,
        effective_date=effective_date,
        runtime_context=runtime_context.strip(),
        tools=list(tools) if tools is not None else None,
        knowledge_docs=list(knowledge_docs) if knowledge_docs is not None else None,
    )
    prompt = REVIEW_USER_PROMPT
    try:
        output_type = (
            AuditFormWithFinancialsResult
            if deps.canonical.form_kind == "financial"
            else AuditFormResult
        )
        started_at = time.perf_counter()
        with agent.override(
            instructions=_mode_instructions(agent, system_prompt or DEFAULT_REVIEW_INSTRUCTIONS)
        ):
            result = await agent.run(
                user_prompt=prompt,
                deps=deps,
                output_type=output_type,
                capabilities=capabilities,
            )
        _populate_runtime_metadata(
            result.output,
            deps=deps,
            usage=result.usage(),
            model_config=model_config,
            source="file_review_agent",
            started_at=started_at,
        )
    except Exception as exc:
        logger.exception(
            "File review agent failed for %s@%s",
            deps.form_definition.id,
            deps.form_definition.version,
        )
        raise RuntimeError(
            _agent_failure_message(exc, deps=deps, prompt=prompt, model_config=model_config)
        ) from exc
    return result.output


async def run_synthetic_review_agent(
    claim_number: str,
    effective_date: str,
    instructions: str,
    path_to_questionnaire: str = "",
    user_prompt: str = "",
    active_settings: Settings | None = None,
    model_name: str | None = None,
) -> AuditResult:
    active_settings = active_settings or settings
    model_config = active_settings.audit_llm_config(model_name=model_name)
    agent = build_file_review_agent(active_settings, model_config=model_config)
    deps = FileReviewAgentDeps(
        path_to_questionnaire=path_to_questionnaire,
        claim_number=claim_number,
        effective_date=effective_date,
        runtime_context=build_runtime_context(user_prompt, instructions),
        tools=[],
        knowledge_docs=[],
        include_state_compliance=False,
    )
    prompt = REVIEW_USER_PROMPT
    try:
        output_type = (
            AuditFormWithFinancialsResult
            if deps.canonical.form_kind == "financial"
            else AuditFormResult
        )
        started_at = time.perf_counter()
        with agent.override(
            instructions=_mode_instructions(agent, SYNTHETIC_REVIEW_INSTRUCTIONS),
            tools=(),
            toolsets=(),
            builtin_tools=(),
        ):
            result = await agent.run(user_prompt=prompt, deps=deps, output_type=output_type)
        _populate_runtime_metadata(
            result.output,
            deps=deps,
            usage=result.usage(),
            model_config=model_config,
            source="synthetic_review_agent",
            started_at=started_at,
        )
    except Exception as exc:
        logger.exception(
            "Synthetic review agent failed for %s@%s",
            deps.form_definition.id,
            deps.form_definition.version,
        )
        raise RuntimeError(
            _agent_failure_message(exc, deps=deps, prompt=prompt, model_config=model_config)
        ) from exc
    return result.output


async def run_completed_intake_agent(
    *,
    document_text: str,
    document_name: str,
    path_to_questionnaire: str,
    instructions: str = "",
    active_settings: Settings | None = None,
    model_name: str | None = None,
) -> CompletedAuditIntakeResult | CompletedFinancialAuditIntakeResult | AuditIntakeFailure:
    active_settings = active_settings or settings
    model_config = active_settings.audit_llm_config(model_name=model_name)
    agent = build_file_review_agent(active_settings, model_config=model_config)
    runtime_context = "\n\n".join(
        part
        for part in [
            f"Document Name: {document_name}",
            f"Additional Intake Instructions:\n{instructions}" if instructions else "",
            "Completed Audit Document Content:",
            document_text,
        ]
        if part
    )
    deps = FileReviewAgentDeps(
        path_to_questionnaire=path_to_questionnaire,
        runtime_context=runtime_context,
        tools=[],
        knowledge_docs=[],
        include_state_compliance=False,
    )
    prompt = REVIEW_USER_PROMPT
    try:
        output_type = (
            CompletedFinancialAuditIntakeResult | AuditIntakeFailure
            if deps.canonical.form_kind == "financial"
            else CompletedAuditIntakeResult | AuditIntakeFailure
        )
        started_at = time.perf_counter()
        with agent.override(
            instructions=_mode_instructions(agent, COMPLETED_INTAKE_INSTRUCTIONS),
            tools=(),
            toolsets=(),
            builtin_tools=(),
        ):
            result = await agent.run(
                user_prompt=prompt,
                deps=deps,
                output_type=output_type,
            )
        if not isinstance(result.output, AuditIntakeFailure):
            _populate_runtime_metadata(
                result.output.result,
                deps=deps,
                usage=result.usage(),
                model_config=model_config,
                source="completed_intake_agent",
                started_at=started_at,
            )
        else:
            deps.cost_tracker.add_usage(
                result.usage(),
                model_config,
                source="completed_intake_agent",
            )
    except Exception as exc:
        logger.exception(
            "Completed intake agent failed for %s@%s",
            deps.form_definition.id,
            deps.form_definition.version,
        )
        raise RuntimeError(
            _agent_failure_message(exc, deps=deps, prompt=prompt, model_config=model_config)
        ) from exc
    return result.output


def build_runtime_context(*parts: str) -> str:
    seen: set[str] = set()
    context_parts: list[str] = []
    for part in parts:
        normalized = part.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        context_parts.append(normalized)
    return "\n\n".join(context_parts)
