"""A2UI transport contracts for agent-rendered chat components."""

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class A2UIComponent(BaseModel):
    """Component payload emitted through AG-UI state and rendered by the frontend."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str
    props: dict[str, Any] = Field(default_factory=dict)
    children: list["A2UIComponent"] = Field(default_factory=list)
    layout: dict[str, Any] | None = None
    styling: dict[str, Any] | None = None
    zone: str | None = "chat"
