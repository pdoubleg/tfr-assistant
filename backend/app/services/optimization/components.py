from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from app.agents.review_agent import DEFAULT_REVIEW_INSTRUCTIONS

OPTIMIZABLE_COMPONENTS: tuple[str, ...] = ("instructions",)


def strip_surrogate_characters(text: str) -> str:
    return "".join(char for char in text if not 0xD800 <= ord(char) <= 0xDFFF)


def normalize_component_text(value: Any) -> str:
    """Normalize prompt component values to safe string representations.

    Ported from gepadantic so GEPA candidates stay UTF-8-safe and readable.
    """

    if value is None:
        return ""
    if isinstance(value, str):
        return strip_surrogate_characters(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        joined = "\n\n".join(str(part) for part in value if part)
        return strip_surrogate_characters(joined)
    return strip_surrogate_characters(str(value))


def normalize_instruction(value: str | None) -> str:
    text = normalize_component_text(value).strip()
    return text or DEFAULT_REVIEW_INSTRUCTIONS


def instruction_callables(agent: Any) -> tuple[Any, ...]:
    instructions = getattr(agent, "_instructions", ())
    return tuple(part for part in instructions if not isinstance(part, str) and callable(part))


def seed_candidate_from_instructions(instructions: str | None) -> dict[str, str]:
    return {"instructions": normalize_instruction(instructions)}


def component_names() -> list[str]:
    return list(OPTIMIZABLE_COMPONENTS)


class AuditPromptProgram:
    """Apply GEPA prompt components to the review agent at runtime.

    V1 exposes only `instructions`, but this keeps candidates as dictionaries so
    future prompt parts can be added without reshaping the adapter contract.
    """

    def __init__(self, candidate: dict[str, str]) -> None:
        self.candidate = candidate

    def render_instructions(self) -> str:
        return normalize_instruction(self.candidate.get("instructions"))

    @contextmanager
    def apply_to(self, agent: Any) -> Iterator[None]:
        with agent.override(
            instructions=(self.render_instructions(), *instruction_callables(agent)),
        ):
            yield
