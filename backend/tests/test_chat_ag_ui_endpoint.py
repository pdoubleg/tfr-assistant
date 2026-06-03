from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.chat import router


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
    app.include_router(router, prefix="/api/chat")
    client = TestClient(app)

    response = client.get("/api/chat/models")

    assert response.status_code == 200
    body = response.json()
    assert body["default_model_name"] == "gpt-5.4-mini"
    mini = next(model for model in body["models"] if model["name"] == "gpt-5.4-mini")
    assert mini["context_window"] == 400_000
