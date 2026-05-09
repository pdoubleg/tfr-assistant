# TFR Backend

FastAPI backend for the Targeted File Review application.

## Shape

- `app/models`: Pydantic domain contracts centered on audit form outputs.
- `app/schemas`: API request/response models.
- `app/agents`: Pydantic-AI agent factories for chat and file-review workers.
- `app/services`: Persistence and catalog helpers. These are intentionally thin so they can move to a database-backed repository layer later.
- `app/api/routers`: FastAPI app routers.

## Run

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

The chat agent defaults to Pydantic-AI's local test model so the UI can stream without external credentials. Set `TFR_CHAT_MODEL=openai:gpt-4o-mini` plus the provider API key when you want live model calls.
