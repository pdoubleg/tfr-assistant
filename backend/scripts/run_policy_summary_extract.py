"""Run policy-summary extraction against PDFs in the backend workspace.

Run from ``backend``:

    uv run python scripts/run_policy_summary_extract.py \
        --effective-date 2026-06-20 \
        --focus-area "hail roof valuation" \
        --pages-per-chunk 6 \
        --output data/workspace/policy_summary_extract.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.tools.policy_summary import (  # noqa: E402
    async_build_policy_summary_report,
    discover_workspace_pdf_paths,
    resolve_workspace_dir,
)
from app.core.config import Settings  # noqa: E402
from app.core.llm import LLMRunCostTracker  # noqa: E402


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> int:
    settings = Settings()
    workspace_dir = resolve_workspace_dir(args.workspace_dir or settings.agent_workspace_dir)
    pdf_paths = discover_workspace_pdf_paths(workspace_dir)
    if args.max_pdfs is not None:
        pdf_paths = pdf_paths[: args.max_pdfs]

    if not pdf_paths:
        print(f"No PDF files found under {workspace_dir}", file=sys.stderr)
        return 1

    output_path = _resolve_output_path(args.output, workspace_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    filter_model_config = settings.policy_summary_filter_llm_config()
    extraction_model_config = settings.policy_summary_extraction_llm_config()
    synthesis_model_config = settings.policy_summary_synthesis_llm_config()
    cost_tracker = LLMRunCostTracker()

    print(f"Workspace: {workspace_dir}")
    print(f"PDFs: {len(pdf_paths)}")
    for path in pdf_paths:
        print(f"- {path}")
    print(f"Filter model: {filter_model_config.label}")
    print(f"Extraction model: {extraction_model_config.label}")
    print(f"Synthesis model: {synthesis_model_config.label}")
    print(f"Effective date: {args.effective_date or 'not supplied'}")
    print(f"Focus area: {args.focus_area or 'not supplied'}")
    print(
        "Chunking: "
        f"pages_per_chunk={args.pages_per_chunk}, "
        f"overlap_pages={args.overlap_pages}, "
        f"max_chars_per_chunk={args.max_chars_per_chunk}"
    )
    focus_filter_mode = "none" if args.include_unrelated_chunks else args.focus_filter_mode
    print(f"Focus filter mode: {focus_filter_mode}")

    report = await async_build_policy_summary_report(
        pdf_paths,
        effective_date=args.effective_date,
        focus_area=args.focus_area,
        pages_per_chunk=args.pages_per_chunk,
        overlap_pages=args.overlap_pages,
        max_chars_per_chunk=args.max_chars_per_chunk,
        pdf_concurrency=args.pdf_concurrency,
        llm_concurrency=args.llm_concurrency,
        model_config=extraction_model_config,
        filter_model_config=filter_model_config,
        synthesis_model_config=synthesis_model_config,
        cost_tracker=cost_tracker,
        skip_obviously_unrelated_chunks=not args.include_unrelated_chunks,
        focus_filter_mode=focus_filter_mode,
        synthesize=not args.no_synthesis,
        max_items_for_synthesis=args.max_items_for_synthesis,
        max_report_points=args.max_report_points,
    )
    output_path.write_text(report, encoding="utf-8")

    print(f"Wrote: {output_path}")
    print(f"LLM calls: {len(cost_tracker.steps)}")
    print(f"Estimated LLM cost: ${cost_tracker.total_cost:.8f}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a markdown policy summary extract from PDFs in data/workspace. "
            "Uses policy summary filter, extraction, and synthesis model settings."
        )
    )
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=None,
        help="Directory to search recursively for PDFs. Defaults to Settings.agent_workspace_dir.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Markdown output path. Defaults to <workspace-dir>/policy_summary_extract.md.",
    )
    parser.add_argument(
        "--effective-date",
        default="",
        help="Policy as-of/effective date, such as 2026-06-20 or 06/20/2026.",
    )
    parser.add_argument(
        "--focus-area",
        default="",
        help="Optional claim, peril, coverage, or audit focus area.",
    )
    parser.add_argument(
        "--pages-per-chunk",
        type=_positive_int,
        default=8,
        help="Number of PDF pages included in each extraction chunk.",
    )
    parser.add_argument(
        "--overlap-pages",
        type=_non_negative_int,
        default=1,
        help="Number of pages to overlap between neighboring chunks.",
    )
    parser.add_argument(
        "--max-chars-per-chunk",
        type=_positive_int,
        default=26000,
        help="Hard character cap for each chunk prompt body.",
    )
    parser.add_argument(
        "--pdf-concurrency",
        type=_positive_int,
        default=4,
        help="Concurrent PDF text extraction workers.",
    )
    parser.add_argument(
        "--llm-concurrency",
        type=_positive_int,
        default=8,
        help="Concurrent LLM chunk extraction calls.",
    )
    parser.add_argument(
        "--include-unrelated-chunks",
        action="store_true",
        help=(
            "When focus-area is supplied, send every chunk instead of prefiltering obvious misses. "
            "Equivalent to --focus-filter-mode none."
        ),
    )
    parser.add_argument(
        "--focus-filter-mode",
        choices=("llm", "keyword", "none"),
        default="llm",
        help=(
            "How to prefilter chunks when focus-area is supplied. "
            "llm is conservative and most robust; keyword is faster; none disables filtering."
        ),
    )
    parser.add_argument(
        "--max-pdfs",
        type=_positive_int,
        default=None,
        help="Optional cap on PDFs processed, useful for quick pipeline tests.",
    )
    parser.add_argument(
        "--no-synthesis",
        action="store_true",
        help="Skip the final LLM compression pass and render deterministic concise output.",
    )
    parser.add_argument(
        "--max-items-for-synthesis",
        type=_positive_int,
        default=60,
        help="Maximum extracted items sent to the final compression pass.",
    )
    parser.add_argument(
        "--max-report-points",
        type=_positive_int,
        default=12,
        help="Maximum key policy points in the markdown report.",
    )
    return parser.parse_args()


def _resolve_output_path(output: Path | None, workspace_dir: Path) -> Path:
    if output is None:
        return workspace_dir / "policy_summary_extract.md"
    if output.is_absolute():
        return output
    return (Path.cwd() / output).resolve()


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be greater than or equal to 0")
    return parsed


if __name__ == "__main__":
    sys.exit(main())
