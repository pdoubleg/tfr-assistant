import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from app.core.config import Settings, get_settings
from app.core.llm import LLMModelConfig, LLMRunCostTracker, build_llm_model
from app.models.audit import (
    AuditFormResult,
    AuditFormWithFinancialsResult,
    AuditResult,
    parse_audit_result,
)
from app.schemas.forms import AuditFormDefinition

settings = get_settings()
logger = logging.getLogger(__name__)


DEFAULT_REVIEW_INSTRUCTIONS = (
    "You are a file review worker. Your only job is to complete audit form "
    "questionnaires from file evidence. Use the registered audit form and runtime "
    "context provided in the additional instructions to guide your focus and output.\n"
    "If user requests an example audit, create a fictitious result as a demonstration.\n"
    "Output must validate exactly as the registered audit form result schema. Use only "
    "Yes or No for question answers. If the canonical standard question lists "
    "sub_questions, return only the listed sub_question driver(s) that apply, with "
    "reasoning and citations on each one. Financial audit forms are flat and require "
    "total_amount_reviewed_dollars plus question-level overwrite_dollars and "
    "underwrite_dollars."
)

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
    instructions: str = ""
    tools: list[str] | None = None
    knowledge_docs: list[str] | None = None
    include_form_instructions: bool = True
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
        if self.knowledge_docs is None:
            self.knowledge_docs = list(self.form_definition.knowledge_docs or [])


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
    )

    @agent.instructions
    def add_tfr_template(ctx: RunContext[FileReviewAgentDeps]) -> str:
        definition = ctx.deps.form_definition
        sections = [
            "Registered Audit Form:",
            definition.canonical.as_questionnaire_string(),
        ]
        if ctx.deps.claim_number:
            sections.extend(["", f"Claim Number: {ctx.deps.claim_number}"])
        if ctx.deps.effective_date:
            sections.extend(["", f"Effective Date: {ctx.deps.effective_date}"])
        if ctx.deps.include_form_instructions and definition.instructions:
            sections.extend(
                [
                    "",
                    "Form Instructions:",
                    definition.instructions,
                ]
            )
        if ctx.deps.instructions:
            sections.extend(["", "Additional Runtime Instructions:", ctx.deps.instructions])
        if ctx.deps.tools:
            sections.extend(
                [
                    "",
                    "Selected Agent Tools:",
                    ", ".join(ctx.deps.tools),
                ]
            )
        if ctx.deps.knowledge_docs:
            sections.extend(
                [
                    "",
                    "Knowledge Documents:",
                    "\n".join(f"- {doc}" for doc in ctx.deps.knowledge_docs),
                ]
            )
        return "\n".join(sections)

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


async def run_file_review_agent(
    claim_number: str,
    effective_date: str,
    instructions: str,
    path_to_questionnaire: str = "",
    user_prompt: str = "",
    tools: list[str] | None = None,
    knowledge_docs: list[str] | None = None,
    base_instructions: str | None = None,
    include_form_instructions: bool = True,
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
        instructions=instructions,
        tools=list(tools) if tools is not None else None,
        knowledge_docs=list(knowledge_docs) if knowledge_docs is not None else None,
        include_form_instructions=include_form_instructions,
    )
    prompt = _prompt_with_context(
        user_prompt or "Please run a TFR audit.",
        claim_number=claim_number,
        effective_date=effective_date,
        instructions=instructions,
    )
    try:
        output_type = (
            AuditFormWithFinancialsResult
            if deps.canonical.form_kind == "financial"
            else AuditFormResult
        )
        if base_instructions:
            with agent.override(instructions=_mode_instructions(agent, base_instructions)):
                result = await agent.run(user_prompt=prompt, deps=deps, output_type=output_type)
        else:
            result = await agent.run(user_prompt=prompt, deps=deps, output_type=output_type)
        deps.cost_tracker.add_usage(result.usage(), model_config, source="file_review_agent")
        result.output.cost = deps.cost_tracker.total_cost
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
    knowledge_docs: list[str] | None = None,
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
        instructions=instructions,
        tools=[],
        knowledge_docs=list(knowledge_docs) if knowledge_docs is not None else None,
    )
    prompt = _prompt_with_context(
        user_prompt or instructions or "Generate one synthetic completed audit.",
        claim_number=claim_number,
        effective_date=effective_date,
        instructions=instructions,
    )
    try:
        output_type = (
            AuditFormWithFinancialsResult
            if deps.canonical.form_kind == "financial"
            else AuditFormResult
        )
        with agent.override(
            instructions=_mode_instructions(agent, SYNTHETIC_REVIEW_INSTRUCTIONS),
            tools=(),
            toolsets=(),
            builtin_tools=(),
        ):
            result = await agent.run(user_prompt=prompt, deps=deps, output_type=output_type)
        deps.cost_tracker.add_usage(result.usage(), model_config, source="synthetic_review_agent")
        result.output.cost = deps.cost_tracker.total_cost
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
    knowledge_docs: list[str] | None = None,
    active_settings: Settings | None = None,
    model_name: str | None = None,
) -> CompletedAuditIntakeResult | CompletedFinancialAuditIntakeResult | AuditIntakeFailure:
    active_settings = active_settings or settings
    model_config = active_settings.audit_llm_config(model_name=model_name)
    agent = build_file_review_agent(active_settings, model_config=model_config)
    deps = FileReviewAgentDeps(
        path_to_questionnaire=path_to_questionnaire,
        instructions=instructions,
        tools=[],
        knowledge_docs=list(knowledge_docs) if knowledge_docs is not None else None,
    )
    prompt = "\n\n".join(
        part
        for part in [
            f"Document Name: {document_name}",
            f"Additional Intake Instructions:\n{instructions}" if instructions else "",
            "Completed Audit Document Content:",
            document_text,
        ]
        if part
    )
    try:
        output_type = (
            CompletedFinancialAuditIntakeResult | AuditIntakeFailure
            if deps.canonical.form_kind == "financial"
            else CompletedAuditIntakeResult | AuditIntakeFailure
        )
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
        deps.cost_tracker.add_usage(result.usage(), model_config, source="completed_intake_agent")
        if not isinstance(result.output, AuditIntakeFailure):
            result.output.result.cost = deps.cost_tracker.total_cost
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


def _prompt_with_context(
    prompt: str,
    *,
    claim_number: str = "",
    effective_date: str = "",
    instructions: str = "",
) -> str:
    if claim_number:
        prompt += f"\n\nClaim Number: {claim_number}"
    if effective_date:
        prompt += f"\n\nEffective Date: {effective_date}"
    if instructions:
        prompt += f"\n\nAdditional Instructions: {instructions}"
    return prompt
