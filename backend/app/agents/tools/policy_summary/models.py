from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocType = Literal["policy", "renewal", "endorsement", "declarations", "notice", "other"]
ItemType = Literal[
    "coverage",
    "exclusion",
    "limit",
    "deductible",
    "condition",
    "definition",
    "form",
    "endorsement",
    "schedule",
    "other",
]
Action = Literal["adds", "changes", "replaces", "deletes", "continues", "unknown"]
Status = Literal["effective", "superseded", "deleted", "unclear"]
Relevance = Literal["direct", "potential", "context", "not_relevant"]
Confidence = Literal["high", "medium", "low"]
Priority = Literal["high", "medium", "low"]
FocusFilterMode = Literal["llm", "keyword", "none"]
ReportCategory = Literal[
    "coverage",
    "limit",
    "deductible",
    "exclusion",
    "condition",
    "endorsement",
    "review_flag",
    "other",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Model):
    doc_id: str = ""
    file: str = ""
    page_start: int = 1
    page_end: int = 1
    quote: str = Field(
        default="",
        description="Short exact quote, preferably under 40 words.",
    )

    def label(self) -> str:
        page = (
            f"p. {self.page_start}"
            if self.page_start == self.page_end
            else f"pp. {self.page_start}-{self.page_end}"
        )
        name = self.file or self.doc_id or "source"
        return f"{name}, {page}"


class ExtractedItem(Model):
    item_type: ItemType = "other"
    title: str = Field(default="", description="Concise label, preferably under 12 words.")
    summary: str = Field(
        default="",
        description="Claim-focused explanation, preferably one sentence under 35 words.",
    )
    action: Action = "unknown"
    status: Status = "unclear"
    relevance: Relevance = "context"
    confidence: Confidence = "medium"
    value: str | None = None
    applies_to: str | None = None
    effective_date: str | None = None
    form: str | None = None
    evidence: list[Evidence] = Field(
        default_factory=list,
        description="Only the best one or two citations needed to support this item.",
    )

    def evidence_text(self) -> str:
        if not self.evidence:
            return ""
        return "; ".join(evidence.label() for evidence in self.evidence[:3])


class ChunkExtract(Model):
    """LLM-generated output for one PDF text chunk."""

    doc_type: DocType = "other"
    doc_title: str = ""
    doc_date: str | None = None
    policy_period: str | None = None
    forms: list[str] = Field(default_factory=list)
    items: list[ExtractedItem] = Field(
        default_factory=list,
        description=(
            "Only provisions useful to the claim focus; omit generic unrelated boilerplate."
        ),
    )
    questions: list[str] = Field(
        default_factory=list,
        description=(
            "Only claim-review blockers or ambiguities that remain after reading the chunk."
        ),
    )


class SourceDoc(Model):
    doc_id: str
    file: str
    pages: int
    doc_type: DocType = "other"
    title: str = ""
    doc_date: str | None = None
    policy_period: str | None = None
    forms: list[str] = Field(default_factory=list)


class BuildStats(Model):
    source_pdf_count: int = 0
    total_chunks: int = 0
    selected_chunks: int = 0
    skipped_chunks: int = 0
    extraction_failures: int = 0
    focus_filter_mode: FocusFilterMode = "none"
    focus_filter_failures: int = 0


class PolicySummaryExtract(Model):
    as_of_date: date | None = None
    focus_area: str | None = None
    generated_at: datetime
    sources: list[SourceDoc]
    items: list[ExtractedItem]
    questions: list[str] = Field(default_factory=list)
    stats: BuildStats = Field(default_factory=BuildStats)

    @classmethod
    def build(
        cls,
        *,
        as_of_date: date | None,
        focus_area: str | None,
        sources: list[SourceDoc],
        items: list[ExtractedItem],
        questions: list[str] | None = None,
        stats: BuildStats | None = None,
    ) -> PolicySummaryExtract:
        return cls(
            as_of_date=as_of_date,
            focus_area=focus_area,
            generated_at=datetime.now(UTC),
            sources=sources,
            items=items,
            questions=questions or [],
            stats=stats or BuildStats(),
        )


class FocusedPolicyPoint(Model):
    priority: Priority = "medium"
    category: ReportCategory = "other"
    title: str = Field(default="", description="Short policy-point title.")
    policy_effect: str = Field(
        default="",
        description="Plain-English effect of the provision for the claim review.",
    )
    claim_relevance: str = Field(
        default="",
        description="Why this matters to the supplied focus area or claim issue.",
    )
    citation: str = Field(default="", description="Best citation label, including file and page.")
    quote: str = Field(default="", description="Optional short supporting quote.")


class FocusedPolicyReport(Model):
    overview: str = Field(
        default="",
        description="Two sentences or fewer summarizing the claim-relevant policy posture.",
    )
    key_points: list[FocusedPolicyPoint] = Field(
        default_factory=list,
        description="Highest-value policy points only, sorted by claim relevance.",
    )
    review_flags: list[str] = Field(
        default_factory=list,
        description="Open issues, missing evidence, conflicts, or extraction cautions.",
    )
    omitted_note: str = Field(
        default="",
        description="Brief note when many low-relevance extracted items were omitted.",
    )


class ChunkRelevance(Model):
    keep: bool = Field(
        default=True,
        description="False only when the chunk is clearly unrelated to the claim focus.",
    )
    relevance: Relevance = "potential"
    reason: str = Field(
        default="",
        description="Short explanation for keeping or skipping the chunk.",
    )


class PageText(Model):
    doc_id: str
    file: str
    page: int
    text: str


class PdfText(Model):
    doc_id: str
    path: Path
    file: str
    pages: list[PageText]


class TextChunk(Model):
    chunk_id: str
    doc_id: str
    file: str
    page_start: int
    page_end: int
    text: str


class BuildSettings(Model):
    as_of_date: date | None = None
    focus_area: str | None = None
    pages_per_chunk: int = 8
    overlap_pages: int = 1
    max_chars_per_chunk: int = 26000
    pdf_concurrency: int = 4
    llm_concurrency: int = 8
    skip_obviously_unrelated_chunks: bool = True
    focus_filter_mode: FocusFilterMode = "llm"
