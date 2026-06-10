import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.ui.ag_ui import AGUIAdapter as PydanticAGUIAdapter
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.responses import Response

from app.api.routers import chat as chat_router
from app.api.routers.chat import router
from app.core.config import Settings, get_settings
from app.core.llm import LLMModelAPI
from app.db.models import Base
from app.models.chat_state import TFRChatState
from app.services.chat_threads import ChatThreadService


def test_ag_ui_endpoint_rejects_empty_body_with_clear_message() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/chat")
    client = TestClient(app)

    response = client.post(
        "/api/chat/ag-ui",
        content=b"",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "AG-UI endpoint requires a JSON RunAgentInput request body.",
        "hint": (
            "Use the AG-UI HttpAgent client or POST a RunAgentInput JSON "
            "object with threadId, runId, state, messages, tools, context, "
            "and forwardedProps."
        ),
    }


def test_ag_ui_endpoint_rejects_whitespace_body_with_clear_message() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/chat")
    client = TestClient(app)

    response = client.post(
        "/api/chat/ag-ui",
        content=b" \n\t ",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "AG-UI endpoint requires a JSON RunAgentInput request body."


def test_chat_models_endpoint_returns_defaults() -> None:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: Settings(
        chat_model_api=LLMModelAPI.CHAT,
    )
    app.include_router(router, prefix="/api/chat")
    client = TestClient(app)

    response = client.get("/api/chat/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default_model_name"] == "gpt-5.4-mini"
    assert body["default_reasoning_effort"] is None
    mini = next(model for model in body["models"] if model["name"] == "gpt-5.4-mini")
    assert mini["api"] == "chat"
    assert mini["context_window"] == 400_000
    assert mini["reasoning_efforts"] == []
    assert mini["default_reasoning_effort"] is None


def test_chat_models_endpoint_includes_reasoning_for_responses_api() -> None:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: Settings(
        chat_model_api=LLMModelAPI.RESPONSES,
    )
    app.include_router(router, prefix="/api/chat")
    client = TestClient(app)

    response = client.get("/api/chat/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default_reasoning_effort"] == "low"
    mini = next(model for model in body["models"] if model["name"] == "gpt-5.4-mini")
    assert mini["api"] == "responses"
    assert mini["reasoning_efforts"] == ["minimal", "low", "medium", "high"]
    assert mini["default_reasoning_effort"] == "low"


@pytest.mark.anyio
async def test_ag_ui_endpoint_restores_saved_history_without_latest_user_duplication(
    monkeypatch,
    tmp_path,
) -> None:
    class CapturingAGUIAdapter:
        captured_run_messages = []
        captured_history = []
        captured_conversation_id = None

        def __init__(self, *, run_input, **kwargs) -> None:
            self.run_input = run_input

        @classmethod
        def build_run_input(cls, body: bytes):
            return PydanticAGUIAdapter.build_run_input(body)

        def run_stream(self, **kwargs):
            CapturingAGUIAdapter.captured_run_messages = list(self.run_input.messages)
            CapturingAGUIAdapter.captured_history = list(kwargs["message_history"])
            CapturingAGUIAdapter.captured_conversation_id = kwargs["conversation_id"]

            async def empty_stream():
                if False:
                    yield None

            return empty_stream()

        def streaming_response(self, stream):
            return Response(status_code=204)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        settings = Settings(
            data_dir=tmp_path / "data",
            chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
            chat_model_api=LLMModelAPI.TEST,
        )

        async with session_factory() as session:
            await ChatThreadService(session, settings).upsert_thread(
                thread_id="thread-1",
                messages=[
                    ModelRequest(parts=[UserPromptPart("Original question")]),
                    ModelResponse(parts=[TextPart("Original answer")], model_name="test"),
                ],
                state=TFRChatState(artifact_session_id="session-1"),
                model_name="gpt-5.4-mini",
                reasoning_effort=None,
            )

        monkeypatch.setattr(chat_router, "AGUIAdapter", CapturingAGUIAdapter)
        monkeypatch.setattr(chat_router, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(chat_router, "get_settings", lambda: settings)

        app = FastAPI()
        app.include_router(router, prefix="/api/chat")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat/ag-ui",
                json={
                    "threadId": "thread-1",
                    "runId": "run-1",
                    "state": {},
                    "messages": [
                        {"id": "u1", "role": "user", "content": "Original question"},
                        {"id": "a1", "role": "assistant", "content": "Original answer"},
                        {"id": "u2", "role": "user", "content": "Follow-up question"},
                    ],
                    "tools": [],
                    "context": [],
                    "forwardedProps": {},
                },
            )

        assert response.status_code == 204
        assert CapturingAGUIAdapter.captured_conversation_id == "thread-1"
        assert len(CapturingAGUIAdapter.captured_run_messages) == 1
        assert CapturingAGUIAdapter.captured_run_messages[0].content == "Follow-up question"
        assert len(CapturingAGUIAdapter.captured_history) == 2
        assert CapturingAGUIAdapter.captured_history[0].parts[0].content == "Original question"
        assert CapturingAGUIAdapter.captured_history[1].parts[0].content == "Original answer"
    finally:
        await engine.dispose()
