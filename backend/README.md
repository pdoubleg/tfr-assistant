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

