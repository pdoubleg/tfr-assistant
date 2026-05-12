import logging
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Agent, RunContext

from app.core.config import get_settings
from app.models.audit import AuditFormResult
from app.schemas.forms import AuditFormDefinition

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class FileReviewAgentDeps:
    path_to_questionnaire: str = ""
    claim_number: str = ""
    effective_date: str = ""
    instructions: str = ""
    audit_scope: str = ""
    tool_instructions: str = ""
    form_path: Path = field(init=False)
    form_definition: AuditFormDefinition = field(init=False)
    canonical: AuditFormResult = field(init=False)

    def __post_init__(self) -> None:
        self.form_path = Path(self.path_to_questionnaire or settings.default_questionnaire_path)
        self.form_definition = load_form_definition(self.form_path)
        self.canonical = self.form_definition.canonical


def load_canonical_form(path: str | Path) -> AuditFormResult:
    source = Path(path)
    payload = source.read_text(encoding="utf-8")
    try:
        return AuditFormDefinition.model_validate_json(payload).canonical
    except Exception:
        return AuditFormResult.model_validate_json(payload)


def load_form_definition(path: str | Path) -> AuditFormDefinition:
    source = Path(path)
    payload = source.read_text(encoding="utf-8")
    try:
        return AuditFormDefinition.model_validate_json(payload)
    except Exception:
        canonical = AuditFormResult.model_validate_json(payload)
        return AuditFormDefinition(
            id=canonical.form_id,
            version=canonical.form_version,
            title=canonical.title,
            description=canonical.description,
            canonical=canonical,
        )


def build_file_review_agent() -> Agent[FileReviewAgentDeps, AuditFormResult]:
    agent = Agent(
        settings.audit_model,
        output_type=AuditFormResult,
        deps_type=FileReviewAgentDeps,
        validation_context=lambda ctx: ctx.deps,
        retries=3,
        output_retries=3,
        system_prompt=(
            "You are a file review worker. Your only job is to complete "
            "audit form questionnaires from file evidence. The audit form is provided "
            "below. Use it to guide your focus and output.\n"
            "If user requests an example audit, create a fictitious result as a demonstration.\n"
            "Output must validate exactly as AuditFormResult. Use only Yes or No for question "
            "answers. If the canonical question lists sub_questions, return only the listed "
            "sub_question driver(s) that apply, with reasoning and citations on each one. "
            "Do not include sub_question answer fields; including the sub_question means it "
            "applies. If none apply and the answer is Yes, omit sub_questions or set it to "
            "null/[]. If the canonical question does not list sub_questions, put "
            "question-level reasoning in comments and supporting references in citations."
        ),
    )

    @agent.system_prompt
    def add_tfr_template(ctx: RunContext[FileReviewAgentDeps]) -> str:
        definition = ctx.deps.form_definition
        sections = [definition.canonical.as_questionnaire_string()]
        audit_scope = ctx.deps.audit_scope or definition.audit_scope
        tool_instructions = ctx.deps.tool_instructions or definition.tool_instructions
        if audit_scope:
            sections.extend(
                [
                    "",
                    "Audit Scope:",
                    audit_scope,
                ]
            )
        if tool_instructions:
            sections.extend(
                [
                    "",
                    "Tool Instructions:",
                    tool_instructions,
                ]
            )
        return "\n".join(sections)

    return agent


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
) -> str:
    lines = [
        "File review agent failed.",
        f"Model: {_model_label(settings.audit_model)}",
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
    audit_scope: str = "",
    tool_instructions: str = "",
) -> AuditFormResult:
    agent = build_file_review_agent()
    deps = FileReviewAgentDeps(
        path_to_questionnaire=path_to_questionnaire,
        claim_number=claim_number,
        effective_date=effective_date,
        instructions=instructions,
        audit_scope=audit_scope,
        tool_instructions=tool_instructions,
    )
    prompt = user_prompt or "Please run a TFR audit."
    if claim_number:
        prompt += f"\n\nClaim Number: {claim_number}"
    if effective_date:
        prompt += f"\n\nEffective Date: {effective_date}"
    if instructions:
        prompt += f"\n\nAdditional Instructions: {instructions}"
    try:
        result = await agent.run(user_prompt=prompt, deps=deps)
    except Exception as exc:
        logger.exception(
            "File review agent failed for %s@%s",
            deps.form_definition.id,
            deps.form_definition.version,
        )
        raise RuntimeError(_agent_failure_message(exc, deps=deps, prompt=prompt)) from exc
    return result.output
