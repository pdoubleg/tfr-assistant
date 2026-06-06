import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import Base, ChatThreadORM
from app.models.a2ui import A2UIComponent
from app.models.chat_state import TFRChatState
from app.services.chat_threads import (
    ChatThreadService,
    deserialize_model_messages,
    thread_title,
    thread_to_record,
)


@pytest.mark.anyio
async def test_chat_thread_persistence_round_trips_messages_and_metadata(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
        )
        messages = [
            ModelRequest(parts=[UserPromptPart("  Show   me claims data  ")]),
            ModelResponse(parts=[TextPart("Here are the results.")], model_name="test-model"),
        ]
        state = TFRChatState(
            artifact_session_id="session-1",
            components=[
                A2UIComponent(
                    id="chart-1",
                    type="a2ui.PlotlyChart",
                    props={"title": "Claims"},
                )
            ],
            chat_model_name="gpt-5.4-mini",
            chat_context_window=400_000,
            chat_context_used_tokens=42,
            chat_context_remaining_percent=99.9,
            chat_run_cost=0.001,
            chat_total_cost=0.003,
            chat_last_usage={"input_tokens": 10, "total_tokens": 42},
        )

        async with session_factory() as session:
            thread = await ChatThreadService(session, settings).upsert_thread(
                thread_id="thread-1",
                messages=messages,
                state=state,
                model_name="gpt-5.4-mini",
                reasoning_effort="low",
            )

            assert thread.title == "Show me claims data"
            assert thread.model_name == "gpt-5.4-mini"
            assert thread.reasoning_effort == "low"
            assert thread.artifact_session_id == "session-1"
            assert thread.token_usage_json == {"input_tokens": 10, "total_tokens": 42}
            assert thread.component_anchor_turns_json == {"chart-1": 1}

            restored_messages = deserialize_model_messages(thread.messages_json)
            assert isinstance(restored_messages[0], ModelRequest)
            record = thread_to_record(thread)
            assert record["messages"][0]["role"] == "user"
            assert record["messages"][1]["role"] == "assistant"
            assert record["state"]["components"][0]["id"] == "chart-1"
            assert record["component_anchor_turns"] == {"chart-1": 1}
    finally:
        await engine.dispose()


def test_chat_thread_title_truncates_first_user_message() -> None:
    long_message = "x" * 80

    assert thread_title([ModelRequest(parts=[UserPromptPart(long_message)])]) == "x" * 64


@pytest.mark.anyio
async def test_delete_thread_removes_artifact_session(tmp_path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
        )
        artifact_dir = tmp_path / "data" / "chat_artifacts" / "session-1"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "chart.json").write_text("{}", encoding="utf-8")

        async with session_factory() as session:
            service = ChatThreadService(session, settings)
            await service.upsert_thread(
                thread_id="thread-1",
                messages=[
                    ModelRequest(parts=[UserPromptPart("Make a chart")]),
                    ModelResponse(parts=[TextPart("Done.")], model_name="test-model"),
                ],
                state=TFRChatState(artifact_session_id="session-1"),
                model_name="gpt-5.4-mini",
                reasoning_effort="low",
            )

            await service.delete_thread("thread-1")

            assert await session.get(ChatThreadORM, "thread-1") is None
            assert not artifact_dir.exists()
    finally:
        await engine.dispose()
