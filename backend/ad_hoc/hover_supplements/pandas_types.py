"""Pandas conversion hints carried by Annotated, outside the LLM JSON schema."""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal


@dataclass(frozen=True)
class PandasKind:
    kind: str


Indicator = Annotated[Literal["yes", "no", "unknown"], PandasKind("indicator")]
Count = Annotated[int | None, PandasKind("count")]
Number = Annotated[float | None, PandasKind("number")]
Date = Annotated[date | None, PandasKind("date")]
Text = Annotated[str | None, PandasKind("text")]
Category = PandasKind("category")


def pandas_kind(info):
    """Read Pydantic's retained Annotated metadata."""
    return next((m.kind for m in info.metadata if isinstance(m, PandasKind)), None)
