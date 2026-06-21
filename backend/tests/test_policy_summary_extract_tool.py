from datetime import date

import pytest

from app.agents.tools.policy_summary import discover_workspace_pdf_paths, parse_effective_date
from app.agents.tools.policy_summary.engine import filter_chunks_with_model
from app.agents.tools.policy_summary.markdown import render_policy_summary_markdown
from app.agents.tools.policy_summary.models import (
    BuildSettings,
    BuildStats,
    Evidence,
    ExtractedItem,
    PageText,
    PdfText,
    PolicySummaryExtract,
    SourceDoc,
    TextChunk,
)
from app.agents.tools.policy_summary.pdf import chunk_pdf_text, clean_pdf_text
from app.agents.tools.policy_summary.synthesis import selected_items_for_synthesis
from app.core.config import Settings
from app.core.llm import (
    DEFAULT_POLICY_SUMMARY_EXTRACTION_MODEL_NAME,
    DEFAULT_POLICY_SUMMARY_FILTER_MODEL_NAME,
    DEFAULT_POLICY_SUMMARY_SYNTHESIS_MODEL_NAME,
    LLMModelAPI,
    LLMModelConfig,
    default_policy_summary_extraction_model_name,
    default_policy_summary_filter_model_name,
    default_policy_summary_model_name,
    default_policy_summary_synthesis_model_name,
)


def test_parse_effective_date_accepts_iso_and_common_us_formats() -> None:
    assert parse_effective_date("2026-06-20") == date(2026, 6, 20)
    assert parse_effective_date("06/20/2026") == date(2026, 6, 20)
    assert parse_effective_date("Jun 20, 2026") == date(2026, 6, 20)
    assert parse_effective_date("") is None


def test_discover_workspace_pdf_paths_finds_pdfs_recursively(tmp_path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    policy_pdf = nested / "Policy.PDF"
    policy_pdf.write_bytes(b"%PDF-1.4")
    (nested / "notes.txt").write_text("not a pdf", encoding="utf-8")

    assert discover_workspace_pdf_paths(tmp_path) == [policy_pdf]


def test_clean_and_chunk_pdf_text_preserves_page_ranges(tmp_path) -> None:
    pdf = PdfText(
        doc_id="doc-001-policy",
        path=tmp_path / "policy.pdf",
        file="policy.pdf",
        pages=[
            PageText(doc_id="doc-001-policy", file="policy.pdf", page=1, text="A   B\n\n\nC"),
            PageText(doc_id="doc-001-policy", file="policy.pdf", page=2, text="Coverage terms"),
        ],
    )

    chunks = chunk_pdf_text(pdf, pages_per_chunk=2, overlap_pages=0)

    assert clean_pdf_text("A   B\n\n\nC") == "A B\n\nC"
    assert len(chunks) == 1
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2
    assert "--- PAGE 1 ---" in chunks[0].text


@pytest.mark.parametrize("mode", ["llm", "keyword", "none"])
def test_build_settings_accepts_focus_filter_modes(mode: str) -> None:
    assert BuildSettings(focus_filter_mode=mode).focus_filter_mode == mode


def test_keyword_focus_filter_is_available_without_llm_calls() -> None:
    chunks = [
        TextChunk(
            chunk_id="doc-001-chunk-001",
            doc_id="doc-001",
            file="policy.pdf",
            page_start=1,
            page_end=1,
            text="Common policy declarations.",
        ),
        TextChunk(
            chunk_id="doc-001-chunk-002",
            doc_id="doc-001",
            file="policy.pdf",
            page_start=2,
            page_end=2,
            text="Employee handbook holidays and payroll contacts.",
        ),
        TextChunk(
            chunk_id="doc-001-chunk-003",
            doc_id="doc-001",
            file="policy.pdf",
            page_start=3,
            page_end=3,
            text="Hail roof valuation and deductible terms.",
        ),
    ]
    settings = BuildSettings(
        focus_area="hail roof valuation",
        focus_filter_mode="keyword",
    )

    selected, skipped, failures = asyncio_run_filter(chunks, settings)

    assert [chunk.chunk_id for chunk in selected] == [
        "doc-001-chunk-001",
        "doc-001-chunk-003",
    ]
    assert skipped == 1
    assert failures == 0


def test_policy_summary_llm_configs_have_step_specific_default_models() -> None:
    settings = Settings(_env_file=None)

    filter_config = settings.policy_summary_filter_llm_config()
    extraction_config = settings.policy_summary_extraction_llm_config()
    synthesis_config = settings.policy_summary_synthesis_llm_config()
    legacy_config = settings.policy_summary_llm_config()

    assert DEFAULT_POLICY_SUMMARY_FILTER_MODEL_NAME == "gpt-5.4-nano"
    assert DEFAULT_POLICY_SUMMARY_EXTRACTION_MODEL_NAME == "gpt-5.4-mini"
    assert DEFAULT_POLICY_SUMMARY_SYNTHESIS_MODEL_NAME == "gpt-5.4-mini"
    assert default_policy_summary_filter_model_name() == DEFAULT_POLICY_SUMMARY_FILTER_MODEL_NAME
    assert (
        default_policy_summary_extraction_model_name()
        == DEFAULT_POLICY_SUMMARY_EXTRACTION_MODEL_NAME
    )
    assert (
        default_policy_summary_synthesis_model_name() == DEFAULT_POLICY_SUMMARY_SYNTHESIS_MODEL_NAME
    )
    assert default_policy_summary_model_name() == DEFAULT_POLICY_SUMMARY_EXTRACTION_MODEL_NAME
    assert settings.policy_summary_filter_model == DEFAULT_POLICY_SUMMARY_FILTER_MODEL_NAME
    assert settings.policy_summary_extraction_model == DEFAULT_POLICY_SUMMARY_EXTRACTION_MODEL_NAME
    assert settings.policy_summary_synthesis_model == DEFAULT_POLICY_SUMMARY_SYNTHESIS_MODEL_NAME
    assert filter_config.model_name == DEFAULT_POLICY_SUMMARY_FILTER_MODEL_NAME
    assert extraction_config.model_name == DEFAULT_POLICY_SUMMARY_EXTRACTION_MODEL_NAME
    assert synthesis_config.model_name == DEFAULT_POLICY_SUMMARY_SYNTHESIS_MODEL_NAME
    assert legacy_config.model_name == extraction_config.model_name
    assert extraction_config.model_name != settings.audit_model
    assert filter_config.api == LLMModelAPI.CHAT
    assert extraction_config.api == LLMModelAPI.CHAT
    assert synthesis_config.api == LLMModelAPI.CHAT


def test_selected_items_for_synthesis_prioritizes_focus_relevance() -> None:
    summary = _summary_with_items(
        [
            ExtractedItem(
                item_type="condition",
                title="General notice",
                summary="General notice condition.",
                relevance="context",
                evidence=[Evidence(file="policy.pdf", page_start=2, page_end=2, quote="notice")],
            ),
            ExtractedItem(
                item_type="limit",
                title="Hail roof limit",
                summary="Hail roof damage has a specific limit.",
                relevance="direct",
                value="$10,000",
                evidence=[
                    Evidence(file="policy.pdf", page_start=10, page_end=10, quote="hail roof")
                ],
            ),
        ]
    )

    selected = selected_items_for_synthesis(summary, max_items=1)

    assert selected[0].title == "Hail roof limit"


def test_policy_summary_markdown_is_concise_by_default() -> None:
    summary = _summary_with_items(
        [
            ExtractedItem(
                item_type="coverage",
                title="Roof coverage",
                summary="Roof damage is covered when caused by hail.",
                relevance="direct",
                evidence=[
                    Evidence(
                        file="policy.pdf",
                        page_start=4,
                        page_end=4,
                        quote="We cover direct physical loss caused by hail.",
                    )
                ],
            )
        ]
    )

    markdown = render_policy_summary_markdown(summary, max_points=5)

    assert "# Claim-Focused Policy Summary" in markdown
    assert "## Key policy points" in markdown
    assert "Roof coverage" in markdown
    assert "## Detailed extracted items" not in markdown
    assert "## Citation map" not in markdown


def asyncio_run_filter(
    chunks: list[TextChunk],
    settings: BuildSettings,
) -> tuple[list[TextChunk], int, int]:
    import asyncio

    return asyncio.run(
        filter_chunks_with_model(
            chunks,
            settings,
            LLMModelConfig(model_name="test", api=LLMModelAPI.TEST),
        )
    )


def _summary_with_items(items: list[ExtractedItem]) -> PolicySummaryExtract:
    return PolicySummaryExtract.build(
        as_of_date=date(2026, 6, 20),
        focus_area="hail roof valuation",
        sources=[
            SourceDoc(
                doc_id="doc-001-policy",
                file="policy.pdf",
                pages=12,
                doc_type="policy",
            )
        ],
        items=items,
        stats=BuildStats(source_pdf_count=1, total_chunks=2, selected_chunks=2),
    )
