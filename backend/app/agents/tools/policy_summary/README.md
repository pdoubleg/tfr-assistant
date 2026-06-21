# Policy Summary Extract Tool

This package builds a concise, claim-focused policy summary from PDFs in the backend workspace.
It is used by the review agent through the `get_policy_summary_extract` tool and can also be
run directly from `scripts/run_policy_summary_extract.py`.

The tool intentionally avoids the original pydantic-ai graph and CLI pipeline. The local flow is:

1. Discover policy PDFs in `Settings.agent_workspace_dir`, usually `data/workspace`.
2. Extract clean text from each PDF with PyMuPDF.
3. Chunk text by page ranges with optional overlap.
4. Optionally prefilter chunks using the claim `focus_area`.
   - Default: conservative LLM classification of chunks.
   - Alternatives: deterministic keyword filtering or no filtering.
5. Extract claim-relevant policy items from each selected chunk with the policy summary sub-LLM.
6. Merge, normalize, and dedupe extracted items across chunks and documents.
7. Run a final synthesis pass to compress the strongest findings into a concise report.
8. Render a markdown string for the review agent or test script output.

## Review-Agent Tool

The review agent exposes this registered tool:

```python
async def get_policy_summary_extract(
    effective_date: str,
    focus_area: str = "",
) -> str:
    ...
```

The tool returns a markdown string. `effective_date` is used as the policy as-of date, and
`focus_area` should describe the claim issue, peril, coverage question, or audit focus.

Example focus areas:

```text
hail roof valuation and cosmetic damage
interior water backup exclusion and mitigation duties
business income waiting period and civil authority
deductible, ACV/RCV, depreciation, and matching
```

## Model Configuration

The policy summary workflow has separate model settings for each LLM step:

```python
from app.core.config import Settings

settings = Settings()
filter_model = settings.policy_summary_filter_llm_config()
extraction_model = settings.policy_summary_extraction_llm_config()
synthesis_model = settings.policy_summary_synthesis_llm_config()
```

Current hard-coded defaults:

```text
filter:     DEFAULT_POLICY_SUMMARY_FILTER_MODEL_NAME = "gpt-5.4-nano"
extraction: DEFAULT_POLICY_SUMMARY_EXTRACTION_MODEL_NAME = "gpt-5.4-mini"
synthesis:  DEFAULT_POLICY_SUMMARY_SYNTHESIS_MODEL_NAME = "gpt-5.4-mini"
```

Runtime configuration fields live on `Settings`:

```text
policy_summary_filter_model
policy_summary_filter_model_base_name
policy_summary_filter_model_api
policy_summary_filter_model_timeout_seconds

policy_summary_extraction_model
policy_summary_extraction_model_base_name
policy_summary_extraction_model_api
policy_summary_extraction_model_timeout_seconds

policy_summary_synthesis_model
policy_summary_synthesis_model_base_name
policy_summary_synthesis_model_api
policy_summary_synthesis_model_timeout_seconds
```

## Main Pipeline API

Use `async_build_policy_summary_report` when you want the final markdown report:

```python
from app.agents.tools.policy_summary import (
    async_build_policy_summary_report,
    discover_workspace_pdf_paths,
)
from app.core.config import Settings
from app.core.llm import LLMRunCostTracker

settings = Settings()
pdf_paths = discover_workspace_pdf_paths(settings.agent_workspace_dir)
cost_tracker = LLMRunCostTracker()

markdown = await async_build_policy_summary_report(
    pdf_paths,
    effective_date="2026-06-20",
    focus_area="hail roof valuation",
    pages_per_chunk=8,
    overlap_pages=1,
    max_chars_per_chunk=26000,
    pdf_concurrency=4,
    llm_concurrency=8,
    model_config=settings.policy_summary_extraction_llm_config(),
    filter_model_config=settings.policy_summary_filter_llm_config(),
    synthesis_model_config=settings.policy_summary_synthesis_llm_config(),
    cost_tracker=cost_tracker,
    skip_obviously_unrelated_chunks=True,
    focus_filter_mode="llm",
    synthesize=True,
    max_items_for_synthesis=60,
    max_report_points=12,
)
```

Use `async_build_policy_summary_extract` if you need the structured intermediate
`PolicySummaryExtract` object instead of markdown.

## Standalone Test Script

Run from `backend`:

```powershell
uv run python scripts/run_policy_summary_extract.py `
  --effective-date 2026-06-20 `
  --focus-area "hail roof valuation" `
  --pages-per-chunk 6 `
  --output data/workspace/policy_summary_extract.md
```

Useful script flags:

```text
--workspace-dir PATH              Directory to search recursively for PDFs.
--output PATH                     Markdown output path.
--effective-date TEXT             Policy as-of/effective date.
--focus-area TEXT                 Claim, peril, coverage, or audit focus.
--pages-per-chunk INT             Number of pages in each chunk.
--overlap-pages INT               Page overlap between chunks.
--max-chars-per-chunk INT         Max characters per chunk prompt.
--pdf-concurrency INT             Concurrent PDF text extraction workers.
--llm-concurrency INT             Concurrent chunk extraction calls.
--include-unrelated-chunks        Disable focus prefiltering.
--focus-filter-mode llm|keyword|none
                                  Chunk prefilter strategy when focus-area is supplied.
--max-pdfs INT                    Quick-test cap on PDFs processed.
--no-synthesis                    Skip final LLM synthesis and use deterministic fallback.
--max-items-for-synthesis INT     Max extracted items sent to the final synthesis pass.
--max-report-points INT           Max key policy points in the markdown report.
```

## Core Modules

```text
pdf.py          PDF text extraction and page-based chunking.
focus.py        Focus-term expansion, keyword prefiltering, and item ranking helpers.
filtering.py    Conservative LLM chunk filtering for claim-focused extraction.
prompts.py      Chunk extraction instructions and user prompt builders.
extraction.py   Pydantic-AI extraction agent for one text chunk.
engine.py       Orchestration: load PDFs, chunk, extract, merge, and dedupe.
synthesis.py    Final compression/filtering into FocusedPolicyReport.
markdown.py     Concise markdown renderer for the final report.
pipeline.py     Public async APIs and workspace path helpers.
models.py       Pydantic contracts for extraction, summary, and focused report output.
```

## Output Shape

The default markdown is intentionally concise:

```text
# Claim-Focused Policy Summary
- Focus/as-of/source processing profile

## Bottom line
- Two sentences or fewer.

## Key policy points
- Highest-value coverage, limit, deductible, exclusion, condition, and endorsement points.

## Review flags
- Open questions, missing/conflicting evidence, or extraction cautions.

## Evidence index
- Small citation map for the points used in synthesis.
```

The renderer no longer emits exhaustive source tables, detailed item dumps, or a full citation map
by default. Those were too verbose for the review-agent context window and made large policy sets
hard to use.

## Tuning Notes

- Use a specific `focus_area`; the tool is designed to run alongside a claim.
- Smaller `pages_per_chunk` can improve precision when PDFs have dense forms or schedules.
- Larger `pages_per_chunk` can reduce LLM calls but may increase off-focus extraction.
- Keep `skip_obviously_unrelated_chunks=True` for focused claim use and large document sets.
- Keep `focus_filter_mode="llm"` when accuracy matters. It costs an extra lightweight pass but
  handles synonyms, forms context, and policy language that keyword matching can miss.
- Use `focus_filter_mode="keyword"` for cheaper regression/debug runs.
- Use `focus_filter_mode="none"` or `--include-unrelated-chunks` when validating whether filtering
  is dropping useful chunks.
- Increase `max_items_for_synthesis` when the focus is broad or the policy package has many
  endorsements.
- Lower `max_report_points` when the summary is passed directly into another agent prompt.
- Use `--no-synthesis` only for debugging; normal review-agent use should keep synthesis enabled.
