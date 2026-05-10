from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from app.core.config import get_settings
from app.models.audit import AuditFormResult
from app.schemas.forms import AuditFormDefinition

settings = get_settings()


@dataclass
class FileReviewAgentDeps:
    path_to_questionnaire: str = ""
    claim_number: str = ""
    effective_date: str = ""
    instructions: str = ""
    audit_scope: str = ""
    tool_instructions: str = ""


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
        retries=3,
        output_retries=3,
        system_prompt=(
            "You are a file review worker. Your only job is to complete "
            "audit form questionnaires from file evidence. The audit form is provided "
            "below. Use it to guide your focus and output.\n"
            "If user requests an example audit, create a fictitious result as a demonstration.\n"
            "Output must validate exactly as AuditFormResult. Use only Yes or No for question "
            "answers. If a question answer is Yes, return no sub_questions for that question. "
            "If a question answer is No, include at least one listed sub-question with "
            "answer=true, reasoning, and citations."
        ),
    )

    @agent.system_prompt
    def add_tfr_template(ctx: RunContext[FileReviewAgentDeps]) -> str:
        if not ctx.deps.path_to_questionnaire:
            form_path = settings.default_questionnaire_path
        else:
            form_path = ctx.deps.path_to_questionnaire
        definition = load_form_definition(form_path)
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
    result = await agent.run(user_prompt=prompt, deps=deps)
    return result.output
