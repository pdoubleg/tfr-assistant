"""Persistence helpers for saved AG-UI chat threads."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from ag_ui.core import Message
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    UserPromptPart,
)
from pydantic_ai.ui.ag_ui import AGUIAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.llm import ReasoningEffort
from app.db.models import ChatThreadORM, utc_now
from app.models.chat_state import TFRChatState
from app.services.chat_artifacts import ChatArtifactStore

TITLE_CHAR_LIMIT = 64
DEFAULT_THREAD_TITLE = "New chat"


class ChatThreadNotFoundError(KeyError):
    """Raised when a saved chat thread cannot be found."""


class ChatThreadService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def list_threads(self) -> list[ChatThreadORM]:
        result = await self.session.scalars(
            select(ChatThreadORM).order_by(ChatThreadORM.updated_at.desc())
        )
        return list(result.all())

    async def get_thread(self, thread_id: str) -> ChatThreadORM | None:
        if not thread_id:
            return None
        return await self.session.get(ChatThreadORM, thread_id)

    async def require_thread(self, thread_id: str) -> ChatThreadORM:
        thread = await self.get_thread(thread_id)
        if thread is None:
            raise ChatThreadNotFoundError(thread_id)
        return thread

    async def delete_thread(self, thread_id: str) -> None:
        thread = await self.require_thread(thread_id)
        artifact_session_id = thread.artifact_session_id
        await self.session.delete(thread)
        await self.session.commit()
        self.delete_artifact_session(artifact_session_id)

    async def upsert_thread(
        self,
        *,
        thread_id: str | None,
        messages: list[ModelMessage],
        state: TFRChatState,
        model_name: str,
        reasoning_effort: ReasoningEffort | None,
    ) -> ChatThreadORM:
        resolved_thread_id = thread_id or str(uuid4())
        thread = await self.get_thread(resolved_thread_id)
        serialized_messages = serialize_model_messages(messages)
        state_json = state.model_dump(mode="json")
        token_usage = dict(state.chat_last_usage or {})
        component_anchor_turns = update_component_anchor_turns(
            thread.component_anchor_turns_json if thread else {},
            state,
            messages,
        )
        now = utc_now()

        if thread is None:
            thread = ChatThreadORM(
                id=resolved_thread_id,
                created_at=now,
            )
            self.session.add(thread)

        thread.title = thread_title(messages)
        thread.messages_json = serialized_messages
        thread.state_json = state_json
        thread.component_anchor_turns_json = component_anchor_turns
        thread.model_name = model_name
        thread.reasoning_effort = reasoning_effort
        thread.artifact_session_id = state.artifact_session_id or ""
        thread.token_usage_json = token_usage
        thread.context_window = state.chat_context_window
        thread.context_used_tokens = state.chat_context_used_tokens
        thread.context_remaining_percent = state.chat_context_remaining_percent
        thread.run_cost = state.chat_run_cost
        thread.total_cost = state.chat_total_cost
        thread.updated_at = now

        await self.session.commit()
        await self.session.refresh(thread)
        return thread

    def delete_artifact_session(self, artifact_session_id: str) -> None:
        if not artifact_session_id:
            return
        store = ChatArtifactStore(self.settings)
        root = store.root.resolve()
        target = (root / artifact_session_id).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return
        if target.exists() and target.is_dir():
            shutil.rmtree(target)


def serialize_model_messages(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    return ModelMessagesTypeAdapter.dump_python(messages, mode="json")


def deserialize_model_messages(payload: Any) -> list[ModelMessage]:
    if not payload:
        return []
    return list(ModelMessagesTypeAdapter.validate_python(payload))


def model_messages_to_ag_ui(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    ag_ui_messages = AGUIAdapter.dump_messages(messages)
    return [
        message.model_dump(mode="json", by_alias=True, exclude_none=True)
        for message in ag_ui_messages
    ]


def thread_to_summary(thread: ChatThreadORM) -> dict[str, Any]:
    return {
        "id": thread.id,
        "title": thread.title or DEFAULT_THREAD_TITLE,
        "model_name": thread.model_name or "",
        "reasoning_effort": thread.reasoning_effort,
        "artifact_session_id": thread.artifact_session_id or "",
        "token_usage": thread.token_usage_json or {},
        "context_window": thread.context_window,
        "context_used_tokens": thread.context_used_tokens or 0,
        "context_remaining_percent": thread.context_remaining_percent,
        "run_cost": thread.run_cost or 0.0,
        "total_cost": thread.total_cost or 0.0,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
    }


def thread_to_record(thread: ChatThreadORM) -> dict[str, Any]:
    messages = deserialize_model_messages(thread.messages_json)
    return {
        **thread_to_summary(thread),
        "messages": model_messages_to_ag_ui(messages),
        "state": thread.state_json or {},
        "component_anchor_turns": thread.component_anchor_turns_json or {},
    }


def thread_title(messages: list[ModelMessage]) -> str:
    first_message = _first_user_text(messages)
    if not first_message:
        return DEFAULT_THREAD_TITLE
    normalized = re.sub(r"\s+", " ", first_message).strip()
    return normalized[:TITLE_CHAR_LIMIT] or DEFAULT_THREAD_TITLE


def update_component_anchor_turns(
    current: dict[str, int] | None,
    state: TFRChatState,
    messages: list[ModelMessage],
) -> dict[str, int]:
    component_ids = {component.id for component in state.components}
    user_turn_count = max(1, _count_user_turns(messages))
    anchors: dict[str, int] = {}
    for component_id, value in (current or {}).items():
        if component_id in component_ids:
            try:
                anchors[component_id] = int(value)
            except (TypeError, ValueError):
                anchors[component_id] = user_turn_count
    for component_id in component_ids:
        anchors.setdefault(component_id, user_turn_count)
    return anchors


def _count_user_turns(messages: list[ModelMessage]) -> int:
    return sum(1 for message in messages if _request_user_text(message))


def _first_user_text(messages: list[ModelMessage]) -> str:
    for message in messages:
        text = _request_user_text(message)
        if text:
            return text
    return ""


def _request_user_text(message: ModelMessage) -> str:
    if not isinstance(message, ModelRequest):
        return ""
    parts: list[str] = []
    for part in message.parts:
        if not isinstance(part, UserPromptPart):
            continue
        content = part.content
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(item for item in content if isinstance(item, str))
    return "\n".join(parts).strip()


def latest_user_message(messages: list[Message]) -> list[Message]:
    for message in reversed(messages):
        if getattr(message, "role", None) == "user":
            return [message]
    return []
