"""Sub-LLM text analysis tools for Monty."""

from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
from pydantic_ai import Agent

from app.capabilities.monty.collections.base import (
    MontyRuntimeContext,
    _dataset_handle,
    _require_columns,
)
from app.capabilities.monty.registry import ToolCollection, tool
from app.core.llm import LLMModelConfig, build_llm_model


def _cell_text(value: Any) -> str:
    """Convert a dataframe cell to clean text, treating None/NaN as empty.

    Args:
        value: Raw cell value from a pandas dataframe.

    Returns:
        str: Stripped string form of the value, or "" for missing values.
    """
    if value is None:
        return ""
    # pandas represents missing values in object columns as float NaN.
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _meta_value(value: Any, *, max_chars: int) -> str:
    """Render a metadata cell as a single-line, length-capped string.

    Args:
        value: Raw cell value from a pandas dataframe.
        max_chars: Maximum rendered length before truncation.

    Returns:
        str: Whitespace-collapsed value truncated to a safe header length.
    """
    # Collapse newlines/extra whitespace so the value stays on one header line.
    text = " ".join(_cell_text(value).split())
    if len(text) > max_chars:
        suffix = f"...truncated {len(text) - max_chars} chars"
        text = text[: max_chars - len(suffix)] + suffix
    return text


def _record_header(record_number: int, meta: list[tuple[str, str]]) -> str:
    """Build the delimiter header line that precedes one record's text.

    Args:
        record_number: 1-based number of the record among included rows.
        meta: Ordered (column, value) pairs rendered into the header.

    Returns:
        str: A header line like "=== record 3 | claim_number=CLM-42 ===".
    """
    fields = [f"record {record_number}"] + [f"{name}={value}" for name, value in meta]
    return "=== " + " | ".join(fields) + " ==="


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
        return self.context.settings.monty_rlm_max_batch_size

    @property
    def _max_prompt_chars(self) -> int:
        return self.context.settings.monty_rlm_max_prompt_chars

    @property
    def _max_llm_calls(self) -> int:
        return self.context.settings.monty_rlm_max_llm_calls

    @property
    def _chunk_max_chars(self) -> int:
        return self.context.settings.monty_rlm_chunk_max_chars

    @property
    def _prompt_headroom_chars(self) -> int:
        return self.context.settings.monty_rlm_prompt_headroom_chars

    @property
    def _meta_value_max_chars(self) -> int:
        return self.context.settings.monty_rlm_meta_value_max_chars

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
        variable name. When you plan to send many rows per sub-LLM call, prefer
        dataset_chunks(), which packs rows into prompt-ready chunks with record
        delimiters and metadata headers.

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
    def dataset_chunks(
        self,
        dataset_handle: str,
        text_column: str,
        *,
        metadata_columns: list[str] | None = None,
        max_chars: int | None = None,
        max_records: int | None = None,
        max_rows: int = 1000,
        skip_empty: bool = True,
    ) -> list[str]:
        """Pack dataset rows into sub-LLM-ready text chunks with record delimiters.

        Each chunk is a single self-contained string that starts with a banner
        describing which records it covers, followed by one delimited block per
        row ("=== record N | claim_number=... ==="). Metadata column values are
        rendered into each record's header so a sub-LLM can attribute findings
        to the right record. Prefer this over dataset_texts() plus manual
        joining when sending many rows per sub-LLM call. Records are packed
        greedily in row order and are never split across chunks. If metadata
        columns you need do not exist yet, compute them first (e.g. with SQL
        tools) and pass the new dataset handle here. Check len(chunks) against
        the llm_query_batched() batch limit; raise max_chars to reduce the
        chunk count.

        Args:
            dataset_handle: Input dataset handle.
            text_column: Column containing the free-form text to analyze.
            metadata_columns: Optional columns rendered into each record header,
                e.g. ["claim_number", "form_date"].
            max_chars: Approximate maximum characters of record text per chunk.
                Defaults to the configured chunk size and is silently clamped
                so chunks always leave headroom for your task instructions
                under the sub-LLM prompt limit.
            max_records: Optional cap on records per chunk (useful when the
                sub-LLM task is per-record, like "score each form").
            max_rows: Maximum number of dataset rows to include.
            skip_empty: Whether to omit rows whose text value is empty.

        Returns:
            list[str]: Prompt-ready chunk strings, in dataset row order.

        Examples:
            ```python
            chunks = dataset_chunks(
                "ds_1",
                "form_text",
                metadata_columns=["claim_number", "form_date"],
                max_chars=15000,
            )
            print(len(chunks))
            print(chunks[0][:120])
            task = "Summarize key damage findings per record. Cite claim numbers."
            answers = await llm_query_batched([task + "\\n\\n" + c for c in chunks])
            print(answers[0])
            # Prints
            # 3
            # [chunk 1/3 | source ds_1 | records 1-25 of 64 | text column: form_text]
            # ...
            # Claim CLM-0042 reports wind damage to the roof ridge ...
            ```
        """
        if max_rows < 1:
            raise ValueError("max_rows must be at least 1.")
        if max_records is not None and max_records < 1:
            raise ValueError("max_records must be at least 1 when provided.")
        if max_chars is None:
            max_chars = self._chunk_max_chars
        if max_chars < 1:
            raise ValueError("max_chars must be at least 1.")
        if not isinstance(text_column, str) or not text_column:
            raise ValueError("dataset_chunks requires exactly one text column name.")
        metadata_columns = list(metadata_columns or [])
        if any(not isinstance(column, str) or not column for column in metadata_columns):
            raise ValueError("metadata_columns must be non-empty column names.")
        if text_column in metadata_columns:
            raise ValueError(f"text_column {text_column!r} cannot also be a metadata column.")

        handle = _dataset_handle(dataset_handle)
        dataframe = self._load(handle)
        _require_columns(dataframe, [text_column, *metadata_columns])

        # Clamp instead of raising so chunks always leave headroom for the
        # caller's task instructions under the sub-LLM prompt limit.
        effective_max = min(max_chars, self._max_prompt_chars - self._prompt_headroom_chars)

        # Render one delimited block per included row. Records are expected to
        # be short (a few paragraphs); a block longer than effective_max is not
        # split and simply ends up in its own chunk during packing below.
        blocks: list[tuple[int, str]] = []  # (record_number, block_text)
        record_number = 0
        for _, row in dataframe.head(max_rows).iterrows():
            text = _cell_text(row[text_column])
            if not text and skip_empty:
                continue
            record_number += 1
            meta = [
                (column, _meta_value(row[column], max_chars=self._meta_value_max_chars))
                for column in metadata_columns
            ]
            blocks.append((record_number, f"{_record_header(record_number, meta)}\n{text}"))

        # Greedily pack blocks into chunks, keeping dataset row order.
        groups: list[list[tuple[int, str]]] = []
        current: list[tuple[int, str]] = []
        current_size = 0
        for number, block in blocks:
            added = len(block) + (2 if current else 0)  # +2 for the "\n\n" joiner
            over_chars = current_size + added > effective_max
            over_records = max_records is not None and len(current) >= max_records
            if current and (over_chars or over_records):
                groups.append(current)
                current = []
                current_size = 0
                added = len(block)
            current.append((number, block))
            current_size += added
        if current:
            groups.append(current)

        # Second pass: prepend a banner now that the total chunk count is known.
        total_records = record_number
        chunks: list[str] = []
        for chunk_index, group in enumerate(groups, start=1):
            first, last = group[0][0], group[-1][0]
            banner = (
                f"[chunk {chunk_index}/{len(groups)} | source {handle} | "
                f"records {first}-{last} of {total_records} | "
                f"text column: {text_column}]"
            )
            body = "\n\n".join(block for _, block in group)
            chunks.append(f"{banner}\n\n{body}")
        return chunks

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
