from __future__ import annotations

import asyncio
from collections.abc import Sequence

from pydantic_ai import Agent

from app.core.llm import LLMModelConfig, LLMRunCostTracker, build_llm_model

from .models import BuildSettings, ChunkRelevance, TextChunk

FILTER_INSTRUCTIONS = """
You classify whether a policy PDF text chunk should be read by a claim-focused policy extractor.

The goal is high recall for claim-relevant policy language, not aggressive pruning.
Skip a chunk only when it is clearly unrelated to the focus area and unlikely to affect coverage,
scope, valuation, deductibles, limits, duties, exclusions, forms, schedules, endorsements, or
claim-review questions.

Keep the chunk when it:
- directly mentions the focus area or close policy concepts,
- contains declarations, schedules, forms lists, endorsements, limits, deductibles, exclusions,
  valuation/loss settlement, duties after loss, definitions, or coverage grants that might affect
  the focus,
- provides document identity, policy period, form numbers, or amendment context,
- is ambiguous or you are not confident it is unrelated.

Return keep=false only for clearly unrelated content.
""".strip()


async def llm_select_chunks(
    chunks: Sequence[TextChunk],
    settings: BuildSettings,
    model_config: LLMModelConfig,
    cost_tracker: LLMRunCostTracker | None = None,
) -> tuple[list[TextChunk], int, int]:
    if not settings.focus_area:
        return list(chunks), 0, 0

    agent = Agent(
        build_llm_model(model_config),
        output_type=ChunkRelevance,
        instructions=FILTER_INSTRUCTIONS,
    )
    semaphore = asyncio.Semaphore(max(1, settings.llm_concurrency))
    first_chunk_by_doc: set[str] = set()

    async def classify(chunk: TextChunk) -> tuple[TextChunk, ChunkRelevance | None, bool]:
        is_first_for_doc = chunk.doc_id not in first_chunk_by_doc
        first_chunk_by_doc.add(chunk.doc_id)
        if is_first_for_doc:
            relevance = ChunkRelevance(
                keep=True,
                relevance="context",
                reason="Document context.",
            )
            return chunk, relevance, False

        async with semaphore:
            try:
                result = await agent.run(_build_filter_prompt(chunk, settings))
                if cost_tracker is not None:
                    cost_tracker.add_usage(
                        result.usage(),
                        model_config,
                        source=f"policy_summary_filter:{chunk.chunk_id}",
                    )
                return chunk, result.output, False
            except Exception:
                return chunk, None, True

    results = await asyncio.gather(*(classify(chunk) for chunk in chunks))
    selected: list[TextChunk] = []
    skipped = 0
    failures = 0
    for chunk, relevance, failed in results:
        if failed:
            failures += 1
            selected.append(chunk)
            continue
        if relevance is None or relevance.keep:
            selected.append(chunk)
        else:
            skipped += 1
    return selected, skipped, failures


def _build_filter_prompt(chunk: TextChunk, settings: BuildSettings) -> str:
    as_of = settings.as_of_date.isoformat() if settings.as_of_date else "not supplied"
    return f"""
Classify this policy PDF chunk for claim-focused extraction.

focus_area: {settings.focus_area}
as_of_date: {as_of}
source_file: {chunk.file}
chunk_id: {chunk.chunk_id}
page_range: {chunk.page_start}-{chunk.page_end}

Chunk text:
{chunk.text}
""".strip()
