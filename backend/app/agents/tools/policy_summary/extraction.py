from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic_ai import Agent, RunContext

from app.core.llm import LLMModelConfig, LLMRunCostTracker, build_llm_model

from .models import ChunkExtract, TextChunk
from .prompts import (
    EXTRACTION_INSTRUCTIONS,
    PromptRuntimeContext,
    build_chunk_user_prompt,
    build_runtime_instructions,
)


@dataclass(frozen=True)
class ExtractionDeps:
    as_of_date: date | None
    focus_area: str | None
    source_doc_id: str
    source_file: str
    chunk_id: str
    page_start: int
    page_end: int

    def prompt_context(self) -> PromptRuntimeContext:
        return PromptRuntimeContext(
            as_of_date=self.as_of_date,
            focus_area=self.focus_area,
            source_doc_id=self.source_doc_id,
            source_file=self.source_file,
            chunk_id=self.chunk_id,
            page_start=self.page_start,
            page_end=self.page_end,
        )


def create_extraction_agent(model_config: LLMModelConfig) -> Agent[ExtractionDeps, ChunkExtract]:
    agent = Agent(
        build_llm_model(model_config),
        deps_type=ExtractionDeps,
        output_type=ChunkExtract,
        instructions=EXTRACTION_INSTRUCTIONS,
    )

    @agent.instructions
    def add_runtime_context(ctx: RunContext[ExtractionDeps]) -> str:
        return build_runtime_instructions(ctx.deps.prompt_context())

    return agent


async def extract_chunk(
    chunk: TextChunk,
    *,
    as_of_date: date | None,
    focus_area: str | None,
    agent: Any,
    model_config: LLMModelConfig,
    cost_tracker: LLMRunCostTracker | None = None,
) -> ChunkExtract:
    deps = ExtractionDeps(
        as_of_date=as_of_date,
        focus_area=focus_area,
        source_doc_id=chunk.doc_id,
        source_file=chunk.file,
        chunk_id=chunk.chunk_id,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
    )
    result = await agent.run(build_chunk_user_prompt(chunk), deps=deps)
    if cost_tracker is not None:
        cost_tracker.add_usage(
            result.usage(),
            model_config,
            source=f"policy_summary_extract:{chunk.chunk_id}",
        )
    output: ChunkExtract = result.output
    for item in output.items:
        for evidence in item.evidence:
            if not evidence.doc_id:
                evidence.doc_id = chunk.doc_id
            if not evidence.file:
                evidence.file = chunk.file
            if evidence.page_start <= 0:
                evidence.page_start = chunk.page_start
            if evidence.page_end <= 0:
                evidence.page_end = evidence.page_start
    return output
