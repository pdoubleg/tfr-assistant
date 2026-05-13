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

## Database

Local development defaults to SQLite:

```text
sqlite+aiosqlite:///data/tfr_assistant.db
```

Alembic is the source of truth for persistent database schema changes:

```powershell
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe schema change"
uv run alembic check
```

The app still calls `Base.metadata.create_all()` during startup as a local/dev/test bootstrap convenience for missing tables. Do not use that path as the production migration mechanism, and do not add ad hoc SQLite migrations there. For an existing local SQLite database that already matches the current models but has no Alembic version table, run `uv run alembic stamp head` once after backing it up.

Future Postgres testing can use the root `docker-compose.postgres.yml` service:

```powershell
docker compose -f ..\docker-compose.postgres.yml up -d postgres
```

Example async SQLAlchemy URLs:

```text
postgresql+psycopg://app:app@localhost:5432/app
postgresql+asyncpg://app:app@localhost:5432/app
```

Postgres is optional for normal local development.
