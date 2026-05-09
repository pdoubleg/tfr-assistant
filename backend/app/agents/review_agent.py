from pydantic_ai import Agent

from app.models.audit import AuditFormResult


def build_file_review_agent() -> Agent[None, AuditFormResult]:
    return Agent(
        "openai:gpt-4o",
        result_type=AuditFormResult,
        system_prompt=(
            "You are a batch-oriented file review worker. Your only job is to complete "
            "registered audit questionnaires from file evidence. Return a validated "
            "AuditFormResult and do not provide conversational output."
        ),
    )
