from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from app.core.llm import LLMModelConfig, LLMRunCostTracker

from .engine import build_summary_direct
from .markdown import render_policy_summary_markdown
from .models import BuildSettings, FocusFilterMode, PolicySummaryExtract
from .synthesis import async_build_focused_policy_report

_BACKEND_DIR = Path(__file__).resolve().parents[4]


def parse_effective_date(value: date | str | None) -> date | None:
    if isinstance(value, date):
        return value
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass

    for format_string in ("%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    raise ValueError(
        "effective_date must be an ISO date like 2026-06-20 or a common US date format."
    )


def resolve_workspace_dir(workspace_dir: str | Path) -> Path:
    configured = Path(workspace_dir)
    if configured.is_absolute():
        return configured

    cwd_candidate = (Path.cwd() / configured).resolve()
    backend_candidate = (_BACKEND_DIR / configured).resolve()
    if cwd_candidate.exists() or not backend_candidate.exists():
        return cwd_candidate
    return backend_candidate


def discover_workspace_pdf_paths(workspace_dir: str | Path) -> list[Path]:
    root = resolve_workspace_dir(workspace_dir)
    if not root.exists():
        return []
    return sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"
    )


async def async_build_policy_summary_extract(
    pdf_paths: Sequence[str | Path],
    *,
    effective_date: date | str | None = None,
    focus_area: str | None = None,
    pages_per_chunk: int = 8,
    overlap_pages: int = 1,
    max_chars_per_chunk: int = 26000,
    pdf_concurrency: int = 4,
    llm_concurrency: int = 8,
    model_config: LLMModelConfig,
    filter_model_config: LLMModelConfig | None = None,
    cost_tracker: LLMRunCostTracker | None = None,
    skip_obviously_unrelated_chunks: bool = True,
    focus_filter_mode: FocusFilterMode = "llm",
) -> PolicySummaryExtract:
    if not pdf_paths:
        raise ValueError("At least one PDF path is required")

    settings = BuildSettings(
        as_of_date=parse_effective_date(effective_date),
        focus_area=(focus_area or "").strip() or None,
        pages_per_chunk=pages_per_chunk,
        overlap_pages=overlap_pages,
        max_chars_per_chunk=max_chars_per_chunk,
        pdf_concurrency=pdf_concurrency,
        llm_concurrency=llm_concurrency,
        skip_obviously_unrelated_chunks=skip_obviously_unrelated_chunks,
        focus_filter_mode=focus_filter_mode,
    )
    return await build_summary_direct(
        pdf_paths,
        settings,
        model_config,
        cost_tracker,
        filter_model_config=filter_model_config,
    )


async def async_build_policy_summary_report(
    pdf_paths: Sequence[str | Path],
    *,
    effective_date: date | str | None = None,
    focus_area: str | None = None,
    pages_per_chunk: int = 8,
    overlap_pages: int = 1,
    max_chars_per_chunk: int = 26000,
    pdf_concurrency: int = 4,
    llm_concurrency: int = 8,
    model_config: LLMModelConfig,
    filter_model_config: LLMModelConfig | None = None,
    synthesis_model_config: LLMModelConfig | None = None,
    cost_tracker: LLMRunCostTracker | None = None,
    skip_obviously_unrelated_chunks: bool = True,
    focus_filter_mode: FocusFilterMode = "llm",
    synthesize: bool = True,
    max_items_for_synthesis: int = 60,
    max_report_points: int = 12,
) -> str:
    summary = await async_build_policy_summary_extract(
        pdf_paths,
        effective_date=effective_date,
        focus_area=focus_area,
        pages_per_chunk=pages_per_chunk,
        overlap_pages=overlap_pages,
        max_chars_per_chunk=max_chars_per_chunk,
        pdf_concurrency=pdf_concurrency,
        llm_concurrency=llm_concurrency,
        model_config=model_config,
        filter_model_config=filter_model_config,
        cost_tracker=cost_tracker,
        skip_obviously_unrelated_chunks=skip_obviously_unrelated_chunks,
        focus_filter_mode=focus_filter_mode,
    )
    if not synthesize:
        return render_policy_summary_markdown(summary, max_points=max_report_points)

    try:
        focused_report = await async_build_focused_policy_report(
            summary,
            model_config=synthesis_model_config or model_config,
            cost_tracker=cost_tracker,
            max_items=max_items_for_synthesis,
            max_points=max_report_points,
        )
    except Exception as exc:
        summary.questions.append(
            f"Policy summary synthesis failed; rendered deterministic fallback: "
            f"{type(exc).__name__}: {exc}"
        )
        return render_policy_summary_markdown(summary, max_points=max_report_points)

    return render_policy_summary_markdown(
        summary,
        focused_report=focused_report,
        max_points=max_report_points,
    )
