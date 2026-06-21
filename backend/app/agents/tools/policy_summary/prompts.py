from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .focus import infer_focus_terms
from .models import TextChunk

EXTRACTION_INSTRUCTIONS = """
You extract claim-relevant insurance policy provisions from clean PDF text into a compact
structured object.

Return only facts supported by the supplied chunk. Prefer concise, claim-useful extraction over
exhaustive policy indexing.
Do not invent policy identity, claim facts, missing forms, dates, or limits.
Use short exact quotes for evidence.

The report is used by a claim-review agent. If a focus area is supplied:
- Extract direct and plausibly relevant provisions first.
- Include only nearby contextual provisions that change interpretation of those direct items.
- Omit generic policy administration, unrelated forms, and boilerplate even if it contains words
  like "coverage" or "condition."
- Keep no more than 8 high-value items from one chunk unless the chunk is a schedule or declarations
  page with multiple relevant limits/deductibles.
- Mark relevance as direct, potential, context, or not_relevant.
- For property loss topics, valuation, loss settlement, ACV/RCV, depreciation, cosmetic damage,
  matching, ordinance or law, duties after loss, notice/proof of loss, deductibles, exclusions,
  and endorsement changes are usually at least potentially relevant.

If no focus area is supplied, still avoid broad policy inventory. Capture only provisions a claim
reviewer usually needs: coverage grants, limits, deductibles, valuation/loss settlement, exclusions,
duties, endorsements, declarations schedules, and unresolved conflicts.

Keep each title short, each summary to one sentence, and each evidence quote brief.

Use these literals exactly:
- doc_type: policy, renewal, endorsement, declarations, notice, other
- item_type: coverage, exclusion, limit, deductible, condition, definition, form, endorsement,
  schedule, other
- action: adds, changes, replaces, deletes, continues, unknown
- status: effective, superseded, deleted, unclear
- relevance: direct, potential, context, not_relevant
- confidence: high, medium, low

As-of handling:
- Use the as-of date to identify items not yet effective, expired, deleted, or superseded when the
  chunk itself contains enough information.
- If the chunk only states an endorsement modifies/replaces/deletes something, capture that action.
""".strip()


@dataclass(frozen=True)
class PromptRuntimeContext:
    as_of_date: date | None
    focus_area: str | None
    source_doc_id: str
    source_file: str
    chunk_id: str
    page_start: int
    page_end: int

    @property
    def focus_terms(self) -> tuple[str, ...]:
        return tuple(infer_focus_terms(self.focus_area))


def build_runtime_instructions(ctx: PromptRuntimeContext) -> str:
    as_of = ctx.as_of_date.isoformat() if ctx.as_of_date else "not supplied"
    focus = ctx.focus_area or "not supplied"
    terms = ", ".join(ctx.focus_terms[:100]) if ctx.focus_terms else "not supplied"
    return f"""
Runtime extraction context:
- as_of_date: {as_of}
- focus_area: {focus}
- expanded_focus_terms: {terms}
- source_doc_id: {ctx.source_doc_id}
- source_file: {ctx.source_file}
- chunk_id: {ctx.chunk_id}
- page_range: {ctx.page_start}-{ctx.page_end}

When emitting evidence, use this source_doc_id/source_file and page numbers from the supplied
page markers.
""".strip()


def build_chunk_user_prompt(chunk: TextChunk) -> str:
    return f"""
Extract useful policy-summary facts from this PDF chunk.

Be selective. The downstream report should help answer the claim focus, not restate the policy.

source_doc_id: {chunk.doc_id}
source_file: {chunk.file}
chunk_id: {chunk.chunk_id}
page_range: {chunk.page_start}-{chunk.page_end}

PDF chunk text:
{chunk.text}
""".strip()
