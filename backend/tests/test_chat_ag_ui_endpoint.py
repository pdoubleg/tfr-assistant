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
