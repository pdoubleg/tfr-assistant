from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic_ai import Agent

from app.core.llm import LLMModelConfig, LLMRunCostTracker, build_llm_model

from .focus import focus_score
from .models import (
    ExtractedItem,
    FocusedPolicyPoint,
    FocusedPolicyReport,
    PolicySummaryExtract,
    ReportCategory,
)

SYNTHESIS_INSTRUCTIONS = """
You write concise, claim-focused policy summaries for claim review agents.

Use only the compact extracted evidence payload. Do not invent coverage, exclusions, dates, forms,
limits, or claim facts. Prioritize terms that could change coverage, scope, valuation, deductible,
settlement, duties after loss, exclusions, endorsements, or review outcome.

The output is not a policy inventory. Omit low-value boilerplate, duplicate provisions, and generic
definitions unless they directly affect the focus area. Merge duplicates across documents/forms.

Write for a downstream audit agent:
- overview: no more than two sentences.
- key_points: no more than the requested max points.
- policy_effect: one sentence.
- claim_relevance: one sentence.
- quote: short; omit if it does not add value beyond the citation.
- review_flags: only unresolved conflicts, missing pages/forms, extraction failures, or questions a
  reviewer should resolve before relying on the summary.
""".strip()


def selected_items_for_synthesis(
    summary: PolicySummaryExtract,
    *,
    max_items: int = 60,
) -> list[ExtractedItem]:
    """Select the strongest claim-relevant items before the final LLM compression pass."""

    return sorted(summary.items, key=lambda item: _selection_key(item, summary.focus_area))[
        :max_items
    ]


async def async_build_focused_policy_report(
    summary: PolicySummaryExtract,
    *,
    model_config: LLMModelConfig,
    cost_tracker: LLMRunCostTracker | None = None,
    max_items: int = 60,
    max_points: int = 12,
) -> FocusedPolicyReport:
    selected_items = selected_items_for_synthesis(summary, max_items=max_items)
    if not selected_items:
        return deterministic_focused_policy_report(summary, max_points=max_points)

    agent = Agent(
        build_llm_model(model_config),
        output_type=FocusedPolicyReport,
        instructions=SYNTHESIS_INSTRUCTIONS,
    )
    result = await agent.run(
        _build_synthesis_prompt(
            summary,
            selected_items=selected_items,
            max_points=max_points,
        )
    )
    if cost_tracker is not None:
        cost_tracker.add_usage(result.usage(), model_config, source="policy_summary_synthesis")
    report = result.output
    return _clamp_report(report, max_points=max_points)


def deterministic_focused_policy_report(
    summary: PolicySummaryExtract,
    *,
    max_points: int = 12,
) -> FocusedPolicyReport:
    selected_items = selected_items_for_synthesis(summary, max_items=max_points)
    points = [_point_from_item(item) for item in selected_items[:max_points]]
    overview = _deterministic_overview(summary, points)
    flags = list(summary.questions[:6])
    if summary.stats.extraction_failures:
        flags.append(f"{summary.stats.extraction_failures} extraction chunk(s) failed.")
    omitted = ""
    if len(summary.items) > len(points):
        omitted = f"Omitted {len(summary.items) - len(points)} lower-priority extracted item(s)."
    return FocusedPolicyReport(
        overview=overview,
        key_points=points,
        review_flags=flags[:8],
        omitted_note=omitted,
    )


def _build_synthesis_prompt(
    summary: PolicySummaryExtract,
    *,
    selected_items: Sequence[ExtractedItem],
    max_points: int,
) -> str:
    payload = {
        "as_of_date": summary.as_of_date.isoformat() if summary.as_of_date else None,
        "focus_area": summary.focus_area,
        "max_points": max_points,
        "processing": {
            "source_pdf_count": summary.stats.source_pdf_count,
            "selected_chunks": summary.stats.selected_chunks,
            "total_chunks": summary.stats.total_chunks,
            "skipped_chunks": summary.stats.skipped_chunks,
            "extraction_failures": summary.stats.extraction_failures,
            "total_extracted_items": len(summary.items),
            "items_sent_for_synthesis": len(selected_items),
        },
        "sources": [
            {
                "file": source.file,
                "type": source.doc_type,
                "date": source.doc_date,
                "period": source.policy_period,
                "forms": source.forms[:8],
            }
            for source in summary.sources[:40]
        ],
        "items": [_compact_item(item) for item in selected_items],
        "review_flags": summary.questions[:20],
    }
    return (
        "Create a concise claim-focused policy summary from this extracted policy payload.\n"
        "Return only the structured output.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _compact_item(item: ExtractedItem) -> dict[str, object]:
    evidence = item.evidence[0] if item.evidence else None
    return {
        "type": item.item_type,
        "title": item.title,
        "summary": item.summary,
        "relevance": item.relevance,
        "confidence": item.confidence,
        "status": item.status,
        "action": item.action,
        "value": item.value,
        "applies_to": item.applies_to,
        "effective_date": item.effective_date,
        "form": item.form,
        "citation": evidence.label() if evidence else "",
        "quote": _truncate(evidence.quote if evidence else "", 320),
    }


def _point_from_item(item: ExtractedItem) -> FocusedPolicyPoint:
    evidence = item.evidence[0] if item.evidence else None
    return FocusedPolicyPoint(
        priority=_priority_for_item(item),
        category=_category_for_item(item),
        title=item.title or item.item_type.title(),
        policy_effect=item.summary,
        claim_relevance=_claim_relevance_text(item),
        citation=evidence.label() if evidence else "No citation returned",
        quote=_truncate(evidence.quote if evidence else "", 220),
    )


def _deterministic_overview(
    summary: PolicySummaryExtract,
    points: Sequence[FocusedPolicyPoint],
) -> str:
    focus = summary.focus_area or "the claim review"
    if not points:
        return f"No claim-relevant policy points were extracted for {focus}."
    return (
        f"Extracted {len(points)} claim-relevant policy point(s) for {focus} from "
        f"{summary.stats.source_pdf_count} PDF(s)."
    )


def _selection_key(item: ExtractedItem, focus_area: str | None) -> tuple[int, int, int, int, str]:
    relevance_rank = {"direct": 0, "potential": 1, "context": 2, "not_relevant": 9}.get(
        item.relevance,
        5,
    )
    type_rank = {
        "coverage": 0,
        "limit": 1,
        "deductible": 1,
        "exclusion": 2,
        "condition": 3,
        "endorsement": 4,
        "schedule": 5,
        "form": 6,
        "definition": 7,
        "other": 8,
    }.get(item.item_type, 8)
    confidence_rank = {"high": 0, "medium": 1, "low": 2}.get(item.confidence, 2)
    focus_rank = -focus_score(_item_text(item), focus_area) if focus_area else 0
    evidence_rank = 0 if item.evidence else 1
    return (
        relevance_rank,
        focus_rank,
        type_rank + evidence_rank,
        confidence_rank,
        (item.title or item.summary).lower(),
    )


def _item_text(item: ExtractedItem) -> str:
    return " ".join(
        part
        for part in [
            item.item_type,
            item.title,
            item.summary,
            item.value or "",
            item.applies_to or "",
            item.form or "",
            " ".join(evidence.quote for evidence in item.evidence[:2]),
        ]
        if part
    )


def _priority_for_item(item: ExtractedItem) -> str:
    if item.relevance == "direct" or item.item_type in {"coverage", "limit", "deductible"}:
        return "high"
    if item.relevance == "potential" or item.item_type in {"exclusion", "condition"}:
        return "medium"
    return "low"


def _category_for_item(item: ExtractedItem) -> ReportCategory:
    if item.item_type in {
        "coverage",
        "limit",
        "deductible",
        "exclusion",
        "condition",
        "endorsement",
    }:
        return item.item_type
    if item.item_type in {"form", "schedule"}:
        return "endorsement"
    return "other"


def _claim_relevance_text(item: ExtractedItem) -> str:
    if item.relevance == "direct":
        return "Directly relevant to the supplied claim focus."
    if item.relevance == "potential":
        return "Potentially relevant depending on the claim facts."
    if item.relevance == "context":
        return "Context for interpreting more direct policy terms."
    return "Low relevance to the supplied claim focus."


def _clamp_report(report: FocusedPolicyReport, *, max_points: int) -> FocusedPolicyReport:
    return report.model_copy(
        update={
            "key_points": report.key_points[:max_points],
            "review_flags": report.review_flags[:8],
        }
    )


def _truncate(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
