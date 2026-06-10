"""Sub-LLM text analysis tools for Monty."""

from __future__ import annotations

import asyncio

import pandas as pd
from pydantic_ai import Agent

from app.capabilities.monty.collections.base import (
    DEFAULT_RLM_BATCH_SIZE,
    DEFAULT_RLM_MAX_LLM_CALLS,
    DEFAULT_RLM_PROMPT_CHARS,
    MontyRuntimeContext,
    _dataset_handle,
)
from app.capabilities.monty.registry import ToolCollection, tool
from app.core.llm import LLMModelConfig, build_llm_model


class RLMCollection(ToolCollection):
    """Prepare text rows and query sub-LLMs for semantic analysis."""

    name = "rlm"
    description = (
        "Create text lists from dataset handles and query sub-LLMs for row-level or "
        "chunk-level semantic analysis. Async tools must be called with await, "
        "and all sub-LLM calls share the configured call budget for this artifact session."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    def _load(self, dataset_handle: str) -> pd.DataFrame:
        handle = _dataset_handle(dataset_handle)
        return self.context.store.load_dataset(self.context.state, handle).to_dataframe()

    @property
    def _llm_config(self) -> LLMModelConfig:
        return self.context.settings.monty_rlm_llm_config(
            test_output_text="RLM test response",
        )

    @property
    def _max_batch_size(self) -> int:
        return int(
            getattr(self.context.settings, "monty_rlm_max_batch_size", DEFAULT_RLM_BATCH_SIZE)
        )

    @property
    def _max_prompt_chars(self) -> int:
        return int(
            getattr(self.context.settings, "monty_rlm_max_prompt_chars", DEFAULT_RLM_PROMPT_CHARS)
        )

    @property
    def _max_llm_calls(self) -> int:
        return int(
            getattr(self.context.settings, "monty_rlm_max_llm_calls", DEFAULT_RLM_MAX_LLM_CALLS)
        )

    def _build_agent(self) -> Agent[None, str]:
        return Agent(
            build_llm_model(self._llm_config),
            output_type=str,
            instructions=(
                "You are a focused sub-LLM for semantic analysis of text snippets. "
                "Answer the caller's prompt directly and concisely. If the prompt asks "
                "for extraction, preserve relevant evidence and avoid inventing facts."
            ),
        )

    async def _query_async(self, agent: Agent[None, str], prompt: str) -> str:
        result = await agent.run(prompt)
        self.context.rlm_usage.incr(result.usage())
        return result.output

    @tool
    def dataset_texts(
        self,
        dataset_handle: str,
        column: str,
        *,
        max_rows: int = 1000,
        skip_empty: bool = True,
    ) -> list[str]:
        """Convert one dataset column into a list of one text string per row.

        Use this before llm_query_batched() when a SQL result or transformed
        dataset contains many rows of notes, descriptions, claim text, or other
        free-form fields. Store the returned list in a REPL variable, then build
        prompts from it without printing the whole list. For multiple text
        columns, call this tool once per column and assign each list its own
        variable name.

        Args:
            dataset_handle: Input dataset handle.
            column: Single column name to convert.
            max_rows: Maximum number of rows to convert.
            skip_empty: Whether to omit rows where the selected value is empty.

        Returns:
            list[str]: One text string per included dataset row for the selected column.

        Examples:
            ```python
            notes = dataset_texts("ds_1", "adjuster_note", max_rows=100)
            print(len(notes))
            print(notes[0])
            # Prints
            # 100
            # Roof shingles show wind damage near the ridge.
            ```
        """
        if max_rows < 1:
            raise ValueError("max_rows must be at least 1.")
        if not isinstance(column, str) or not column:
            raise ValueError("dataset_texts requires exactly one column name.")
        dataframe = self._load(dataset_handle)
        if column not in dataframe.columns:
            raise ValueError(f"Unknown dataset column: {column}")

        texts: list[str] = []
        for value in dataframe[column].head(max_rows):
            text = "" if value is None else str(value).strip()
            if text or not skip_empty:
                texts.append(text)
        return texts

    @tool
    async def llm_query(self, prompt: str) -> str:
        """Query a sub-LLM with one prompt string.

        This is an async tool. In Python repl code, call it with await:
        `answer = await llm_query(prompt)`.

        Args:
            prompt: Prompt to send to the sub-LLM.

        Returns:
            str: The sub-LLM response text.

        Examples:
            ```python
            answer = await llm_query(
                "Classify this note as roof, window, or interior: "
                + "Roof shingles show wind damage near the ridge."
            )
            print(answer)
            # Prints
            # roof
            ```
        """
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt cannot be empty.")
        if len(prompt) > self._max_prompt_chars:
            raise ValueError(
                f"prompt is too long: {len(prompt)} characters > {self._max_prompt_chars}"
            )
        self.context.reserve_rlm_calls(1, max_calls=self._max_llm_calls)
        return await self._query_async(self._build_agent(), prompt)

    @tool
    async def llm_query_batched(self, prompts: list[str]) -> list[str]:
        """Query a sub-LLM for multiple prompt strings concurrently.

        Use this when rows or chunks can be analyzed independently. This tool
        preserves result order. In Python repl code, call it with await:
        `answers = await llm_query_batched(prompts)`.

        Args:
            prompts: Prompt strings to send concurrently.

        Returns:
            list[str]: Sub-LLM response text for each prompt, in input order.

        Examples:
            ```python
            notes = dataset_texts("ds_1", "adjuster_note", max_rows=3)
            prompts = [
                "Classify this note as roof, window, or interior: " + note
                for note in notes
            ]
            answers = await llm_query_batched(prompts)
            print(len(answers))
            print(answers[0])
            # Prints
            # 3
            # roof
            ```

            ```python
            report = read_file("reports/long-claim.pdf")
            chunks = [report[i : i + 12000] for i in range(0, len(report), 12000)]
            prompts = ["Summarize this claim report chunk:\\n" + chunk for chunk in chunks]
            summaries = await llm_query_batched(prompts[:6])
            print(len(summaries))
            print(summaries[0])
            # Prints
            # 6
            # The first chunk describes ...
            ```
        """
        if not prompts:
            return []
        if len(prompts) > self._max_batch_size:
            raise ValueError(
                f"Too many prompts for one batch: {len(prompts)} > {self._max_batch_size}. "
                "Split the work into smaller batches."
            )
        normalized: list[str] = []
        for index, prompt in enumerate(prompts):
            text = str(prompt).strip()
            if not text:
                raise ValueError(f"Prompt at index {index} is empty.")
            if len(text) > self._max_prompt_chars:
                raise ValueError(
                    f"Prompt at index {index} is too long: "
                    f"{len(text)} characters > {self._max_prompt_chars}"
                )
            normalized.append(text)

        self.context.reserve_rlm_calls(len(normalized), max_calls=self._max_llm_calls)
        agent = self._build_agent()
        results = await asyncio.gather(
            *(self._query_async(agent, prompt) for prompt in normalized),
            return_exceptions=True,
        )
        output: list[str] = []
        for result in results:
            if isinstance(result, BaseException):
                output.append(f"[ERROR] {result}")
            else:
                output.append(result)
        return output
