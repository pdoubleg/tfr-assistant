from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.llm import DEFAULT_AUDIT_MODEL_NAME
from app.models.audit import AuditResult, FormKind


class ReviewAgentToolName(StrEnum):
    GET_CLAIM_SUMMARY = "get_claim_summary"
    GET_CLAIM_NOTES = "get_claim_notes"
    GET_CLAIM_DOCUMENTS_METADATA = "get_claim_documents_metadata"
    GET_CLAIM_DOCUMENT_CONTENT = "get_claim_document_content"
    GET_POLICY_DOCUMENTS_METADATA = "get_policy_documents_metadata"
    GET_POLICY_DOCUMENT_CONTENT = "get_policy_document_content"
    GET_IMAGE_ANALYSIS = "get_image_analysis"


CLAIM_DOCUMENT_TOOLS = (
    ReviewAgentToolName.GET_CLAIM_DOCUMENTS_METADATA,
    ReviewAgentToolName.GET_CLAIM_DOCUMENT_CONTENT,
)
POLICY_DOCUMENT_TOOLS = (
    ReviewAgentToolName.GET_POLICY_DOCUMENTS_METADATA,
    ReviewAgentToolName.GET_POLICY_DOCUMENT_CONTENT,
)
ALL_REVIEW_AGENT_TOOLS = tuple(tool for tool in ReviewAgentToolName)

_TOOL_ALIASES: dict[str, tuple[ReviewAgentToolName, ...]] = {
    "claim_summary": (ReviewAgentToolName.GET_CLAIM_SUMMARY,),
    "summary": (ReviewAgentToolName.GET_CLAIM_SUMMARY,),
    "notes": (ReviewAgentToolName.GET_CLAIM_NOTES,),
    "claim_notes": (ReviewAgentToolName.GET_CLAIM_NOTES,),
    "documents": CLAIM_DOCUMENT_TOOLS,
    "docs": CLAIM_DOCUMENT_TOOLS,
    "claim_documents": CLAIM_DOCUMENT_TOOLS,
    "claim_docs": CLAIM_DOCUMENT_TOOLS,
    "policy_documents": POLICY_DOCUMENT_TOOLS,
    "policy_docs": POLICY_DOCUMENT_TOOLS,
    "images": (ReviewAgentToolName.GET_IMAGE_ANALYSIS,),
    "image_analysis": (ReviewAgentToolName.GET_IMAGE_ANALYSIS,),
}


def _tool_lookup_key(value: str) -> str:
    return "_".join("".join(char.lower() if char.isalnum() else " " for char in value).split())


def normalize_review_agent_tool_names(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, list):
        return value

    normalized: list[ReviewAgentToolName | str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, ReviewAgentToolName):
            tools = (item,)
        elif isinstance(item, str):
            raw = item.strip()
            if not raw:
                continue
            try:
                tools = (ReviewAgentToolName(raw),)
            except ValueError:
                tools = _TOOL_ALIASES.get(_tool_lookup_key(raw), (raw,))
        else:
            normalized.append(item)
            continue

        for tool in tools:
            tool_value = tool.value if isinstance(tool, ReviewAgentToolName) else tool
            if tool_value in seen:
                continue
            seen.add(tool_value)
            normalized.append(tool)
    return normalized


def _normalize_form_kind(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    canonical = data.get("canonical")
    form_kind = data.get("form_kind") or "standard"
    if isinstance(canonical, dict):
        canonical_kind = canonical.get("form_kind") or form_kind
        canonical = {**canonical, "form_kind": canonical_kind}
        data = {**data, "canonical": canonical, "form_kind": canonical_kind}
    else:
        data = {**data, "form_kind": form_kind}
    return data


class AuditFormDefinition(BaseModel):
    id: str
    version: str
    title: str
    form_kind: FormKind = "standard"
    model_name: str = DEFAULT_AUDIT_MODEL_NAME
    description: str | None = None
    tools: list[ReviewAgentToolName] | None = None
    knowledge_docs: list[str] | None = None
    include_state_compliance: bool = False
    canonical: AuditResult
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("tools", mode="before")
    @classmethod
    def normalize_tools(cls, value: Any) -> Any:
        return normalize_review_agent_tool_names(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_prompt_fields(cls, data: Any) -> Any:
        return _normalize_form_kind(data)

    @model_validator(mode="after")
    def validate_form_kind(self) -> "AuditFormDefinition":
        if self.canonical.form_kind != self.form_kind:
            raise ValueError("form_kind must match canonical.form_kind.")
        return self

    @property
    def catalog_key(self) -> str:
        return f"{self.id}@{self.version}-{self.model_name}"


class AuditFormRegistration(BaseModel):
    id: str
    version: str
    title: str
    form_kind: FormKind = "standard"
    model_name: str = DEFAULT_AUDIT_MODEL_NAME
    description: str | None = None
    tools: list[ReviewAgentToolName] | None = None
    knowledge_docs: list[str] | None = None
    include_state_compliance: bool = False
    canonical: AuditResult

    @field_validator("tools", mode="before")
    @classmethod
    def normalize_tools(cls, value: Any) -> Any:
        return normalize_review_agent_tool_names(value)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_prompt_fields(cls, data: Any) -> Any:
        return _normalize_form_kind(data)

    @model_validator(mode="after")
    def validate_form_kind(self) -> "AuditFormRegistration":
        if self.canonical.form_kind != self.form_kind:
            raise ValueError("form_kind must match canonical.form_kind.")
        return self


class AuditFormSummary(BaseModel):
    id: str
    version: str
    title: str
    form_kind: FormKind = "standard"
    model_name: str = DEFAULT_AUDIT_MODEL_NAME
    description: str | None = None
    tools: list[ReviewAgentToolName] | None = None
    knowledge_docs: list[str] | None = None
    include_state_compliance: bool = False
    question_count: int
    sub_question_count: int = 0
    review_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    last_reviewed_at: datetime | None = None
    created_at: datetime | None = None

    @field_validator("tools", mode="before")
    @classmethod
    def normalize_tools(cls, value: Any) -> Any:
        return normalize_review_agent_tool_names(value)
