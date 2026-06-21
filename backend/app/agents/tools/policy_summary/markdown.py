from __future__ import annotations

from .models import ExtractedItem, FocusedPolicyPoint, FocusedPolicyReport, PolicySummaryExtract
from .synthesis import deterministic_focused_policy_report, selected_items_for_synthesis


def _clean(value: object) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.split())


def _bullet(value: object) -> str:
    return _clean(value) or "-"


def render_policy_summary_markdown(
    summary: PolicySummaryExtract,
    *,
    focused_report: FocusedPolicyReport | None = None,
    max_points: int = 12,
) -> str:
    report = focused_report or deterministic_focused_policy_report(summary, max_points=max_points)
    as_of = summary.as_of_date.isoformat() if summary.as_of_date else "Not supplied"
    focus = summary.focus_area or "Not supplied"

    sections = [
        "<!-- policy-summary-extract:v2-focused -->",
        "# Claim-Focused Policy Summary",
        "",
        f"Focus: {_bullet(focus)}  ",
        f"As-of date: {_bullet(as_of)}  ",
        (
            f"Sources: {summary.stats.source_pdf_count} PDF(s), "
            f"{summary.stats.selected_chunks}/{summary.stats.total_chunks} chunk(s) reviewed"
        ),
        f"Chunk filter: {summary.stats.focus_filter_mode}",
    ]
    if summary.stats.skipped_chunks:
        sections.append(f"Focus prefilter skipped {summary.stats.skipped_chunks} chunk(s).")
    if summary.stats.focus_filter_failures:
        sections.append(
            f"Focus filter failures kept for safety: {summary.stats.focus_filter_failures}."
        )
    if summary.stats.extraction_failures:
        sections.append(
            f"Extraction failures retained as flags: {summary.stats.extraction_failures}."
        )

    if report.overview:
        sections.extend(["", "## Bottom line", _bullet(report.overview)])

    sections.extend(["", "## Key policy points", _points_markdown(report.key_points)])

    flags = list(report.review_flags)
    if report.omitted_note:
        flags.append(report.omitted_note)
    sections.extend(["", "## Review flags", _flags_markdown(flags)])

    selected = selected_items_for_synthesis(summary, max_items=max_points)
    if selected:
        sections.extend(["", "## Evidence index", _evidence_index(selected[:max_points])])

    return "\n".join(sections).strip() + "\n"


def _points_markdown(points: list[FocusedPolicyPoint]) -> str:
    if not points:
        return "- No claim-relevant policy points were extracted."

    lines: list[str] = []
    for point in points:
        title = _bullet(point.title or point.category)
        citation = f" [{_clean(point.citation)}]" if point.citation else ""
        lines.append(f"- **{title}** ({point.priority}/{point.category}){citation}")
        if point.policy_effect:
            lines.append(f"  Effect: {_bullet(point.policy_effect)}")
        if point.claim_relevance:
            lines.append(f"  Relevance: {_bullet(point.claim_relevance)}")
        if point.quote:
            lines.append(f'  Quote: "{_bullet(point.quote)}"')
    return "\n".join(lines)


def _flags_markdown(flags: list[str]) -> str:
    cleaned = [_bullet(flag) for flag in flags if _clean(flag)]
    if not cleaned:
        return "- None."
    return "\n".join(f"- {flag}" for flag in cleaned[:8])


def _evidence_index(items: list[ExtractedItem]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for item in items:
        evidence = item.evidence[0] if item.evidence else None
        if not evidence:
            continue
        label = evidence.label()
        key = f"{item.title}|{label}"
        if key in seen:
            continue
        seen.add(key)
        value = f"{item.item_type}: {item.title or item.summary}"
        lines.append(f"- {_bullet(value)} -> {_bullet(label)}")
    return "\n".join(lines[:12]) or "- No citations returned."
