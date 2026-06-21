from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core.llm import LLMModelConfig, LLMRunCostTracker

from .extraction import create_extraction_agent, extract_chunk
from .filtering import llm_select_chunks
from .focus import dedupe_items, select_chunks
from .models import (
    BuildSettings,
    BuildStats,
    ChunkExtract,
    ExtractedItem,
    PdfText,
    PolicySummaryExtract,
    SourceDoc,
    TextChunk,
)
from .pdf import chunk_many_pdfs, extract_many_pdfs


@dataclass(frozen=True)
class ExtractionOutcome:
    chunk: TextChunk
    extract: ChunkExtract | None = None
    error: BaseException | None = None


def unique_values(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = " ".join(value.split())
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)
    return out


def normalize_item(item: ExtractedItem, chunk: TextChunk) -> ExtractedItem:
    for evidence in item.evidence:
        if not evidence.doc_id:
            evidence.doc_id = chunk.doc_id
        if not evidence.file:
            evidence.file = chunk.file
        if evidence.page_start <= 0:
            evidence.page_start = chunk.page_start
        if evidence.page_end <= 0:
            evidence.page_end = evidence.page_start
    return item


async def load_pdfs(paths: Sequence[str | Path], settings: BuildSettings) -> list[PdfText]:
    if not paths:
        raise ValueError("At least one PDF path is required")
    return await extract_many_pdfs(paths, concurrency=settings.pdf_concurrency)


def make_chunks(pdfs: Sequence[PdfText], settings: BuildSettings) -> list[TextChunk]:
    return chunk_many_pdfs(
        pdfs,
        pages_per_chunk=settings.pages_per_chunk,
        overlap_pages=settings.overlap_pages,
        max_chars_per_chunk=settings.max_chars_per_chunk,
    )


async def filter_chunks(
    chunks: Sequence[TextChunk],
    settings: BuildSettings,
) -> tuple[list[TextChunk], int, int]:
    chunk_list = list(chunks)
    if not settings.focus_area or not settings.skip_obviously_unrelated_chunks:
        return chunk_list, 0, 0
    if settings.focus_filter_mode == "none":
        return chunk_list, 0, 0
    if settings.focus_filter_mode == "keyword":
        selected, skipped = select_chunks(chunk_list, settings.focus_area)
        return selected, skipped, 0
    raise ValueError("LLM filtering requires model_config; call filter_chunks_with_model.")


async def filter_chunks_with_model(
    chunks: Sequence[TextChunk],
    settings: BuildSettings,
    filter_model_config: LLMModelConfig,
    cost_tracker: LLMRunCostTracker | None = None,
) -> tuple[list[TextChunk], int, int]:
    if settings.focus_filter_mode != "llm":
        return await filter_chunks(chunks, settings)
    if not settings.focus_area or not settings.skip_obviously_unrelated_chunks:
        return list(chunks), 0, 0
    return await llm_select_chunks(chunks, settings, filter_model_config, cost_tracker)


async def extract_all_chunks(
    chunks: Sequence[TextChunk],
    settings: BuildSettings,
    model_config: LLMModelConfig,
    cost_tracker: LLMRunCostTracker | None = None,
) -> list[ExtractionOutcome]:
    if not chunks:
        return []

    agent = create_extraction_agent(model_config)
    semaphore = asyncio.Semaphore(max(1, settings.llm_concurrency))

    async def run_one(chunk: TextChunk) -> ExtractionOutcome:
        async with semaphore:
            try:
                extract = await extract_chunk(
                    chunk,
                    as_of_date=settings.as_of_date,
                    focus_area=settings.focus_area,
                    agent=agent,
                    model_config=model_config,
                    cost_tracker=cost_tracker,
                )
                return ExtractionOutcome(chunk=chunk, extract=extract)
            except BaseException as exc:
                return ExtractionOutcome(chunk=chunk, error=exc)

    return list(await asyncio.gather(*(run_one(chunk) for chunk in chunks)))


def merge_sources(
    pdfs: Sequence[PdfText],
    outcomes: Sequence[ExtractionOutcome],
) -> list[SourceDoc]:
    by_doc: dict[str, SourceDoc] = {
        pdf.doc_id: SourceDoc(doc_id=pdf.doc_id, file=pdf.file, pages=len(pdf.pages))
        for pdf in pdfs
    }
    forms_by_doc: dict[str, list[str]] = {pdf.doc_id: [] for pdf in pdfs}

    for outcome in outcomes:
        if not outcome.extract:
            continue
        chunk = outcome.chunk
        extract = outcome.extract
        source = by_doc[chunk.doc_id]
        if source.doc_type == "other" and extract.doc_type != "other":
            source.doc_type = extract.doc_type
        if not source.title and extract.doc_title:
            source.title = extract.doc_title
        if not source.doc_date and extract.doc_date:
            source.doc_date = extract.doc_date
        if not source.policy_period and extract.policy_period:
            source.policy_period = extract.policy_period
        forms_by_doc[chunk.doc_id].extend(extract.forms)
        for item in extract.items:
            if item.form:
                forms_by_doc[chunk.doc_id].append(item.form)

    for doc_id, forms in forms_by_doc.items():
        by_doc[doc_id].forms = unique_values(forms)
    return list(by_doc.values())


def merge_items(
    outcomes: Sequence[ExtractionOutcome],
    settings: BuildSettings,
) -> list[ExtractedItem]:
    items: list[ExtractedItem] = []
    for outcome in outcomes:
        if not outcome.extract:
            continue
        for item in outcome.extract.items:
            normalized = normalize_item(item, outcome.chunk)
            if settings.focus_area and normalized.relevance == "not_relevant":
                continue
            items.append(normalized)
    return dedupe_items(items)


def merge_questions(outcomes: Sequence[ExtractionOutcome]) -> list[str]:
    questions: list[str] = []
    for outcome in outcomes:
        chunk = outcome.chunk
        if outcome.extract:
            for question in outcome.extract.questions:
                questions.append(
                    f"{chunk.file} pp. {chunk.page_start}-{chunk.page_end}: {question}"
                )
        if outcome.error:
            questions.append(
                f"Extraction failed for {chunk.file} pp. {chunk.page_start}-{chunk.page_end}: "
                f"{type(outcome.error).__name__}: {outcome.error}"
            )
    return unique_values(questions)


def assemble_summary(
    *,
    pdfs: Sequence[PdfText],
    all_chunks: Sequence[TextChunk],
    selected_chunks: Sequence[TextChunk],
    skipped_chunks: int,
    filter_failures: int,
    outcomes: Sequence[ExtractionOutcome],
    settings: BuildSettings,
) -> PolicySummaryExtract:
    stats = BuildStats(
        source_pdf_count=len(pdfs),
        total_chunks=len(all_chunks),
        selected_chunks=len(selected_chunks),
        skipped_chunks=skipped_chunks,
        extraction_failures=sum(1 for outcome in outcomes if outcome.error is not None),
        focus_filter_mode=(
            settings.focus_filter_mode
            if settings.focus_area and settings.skip_obviously_unrelated_chunks
            else "none"
        ),
        focus_filter_failures=filter_failures,
    )
    return PolicySummaryExtract.build(
        as_of_date=settings.as_of_date,
        focus_area=settings.focus_area,
        sources=merge_sources(pdfs, outcomes),
        items=merge_items(outcomes, settings),
        questions=merge_questions(outcomes),
        stats=stats,
    )


async def build_summary_direct(
    paths: Sequence[str | Path],
    settings: BuildSettings,
    model_config: LLMModelConfig,
    cost_tracker: LLMRunCostTracker | None = None,
    filter_model_config: LLMModelConfig | None = None,
) -> PolicySummaryExtract:
    pdfs = await load_pdfs(paths, settings)
    all_chunks = make_chunks(pdfs, settings)
    selected_chunks, skipped_chunks, filter_failures = await filter_chunks_with_model(
        all_chunks,
        settings,
        filter_model_config or model_config,
        cost_tracker,
    )
    outcomes = await extract_all_chunks(
        selected_chunks,
        settings,
        model_config,
        cost_tracker,
    )
    return assemble_summary(
        pdfs=pdfs,
        all_chunks=all_chunks,
        selected_chunks=selected_chunks,
        skipped_chunks=skipped_chunks,
        filter_failures=filter_failures,
        outcomes=outcomes,
        settings=settings,
    )
