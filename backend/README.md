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

The chat agent defaults to `CHAT_MODEL=gpt-5.4-mini`. Set `CHAT_MODEL_API=test` for local streaming without external credentials, or set `CHAT_MODEL_API=responses` / `chat` for OpenAI-backed runs. Selectable chat/form models are registered in `app.core.llm`; each option has a base pricing name and a deployment name. For Azure OpenAI deployment aliases, set `LLM_DEPLOYMENTS` as JSON, for example `{"gpt-5.4-mini":"gpt-5.4-mini-2026-03-17-us-data-zone"}`, or set `*_MODEL_BASE_NAME` when a role default points directly at a custom deployment. Model names should not use Pydantic-AI prefixes such as `openai-responses:`. Tune `CHAT_MODEL_REASONING_EFFORT`, `CHAT_MODEL_REASONING_SUMMARY`, and `CHAT_MODEL_TIMEOUT_SECONDS` as needed.

## Policy Summary Extract

The review-agent policy summary tool can also be run directly against PDFs in `data/workspace`:

```powershell
uv run python scripts/run_policy_summary_extract.py `
  --effective-date 2026-06-20 `
  --focus-area "hail roof valuation" `
  --pages-per-chunk 6 `
  --output data/workspace/policy_summary_extract.md
```

The script uses the policy summary filter, extraction, and synthesis LLM configs and writes a
markdown report.
By default it runs a final synthesis step that compresses extracted provisions into a concise
claim-focused summary. Use `--no-synthesis` to inspect the deterministic fallback, or tune
`--max-items-for-synthesis` and `--max-report-points` for large policy document sets.
Focused runs default to `--focus-filter-mode llm`, a conservative chunk relevance pass. Use
`--focus-filter-mode keyword` for cheaper comparisons or `--focus-filter-mode none` to disable
prefiltering.

## Output bundles

Monty can render report bundles as HTML plus `data.xlsx`, and deck bundles as PPTX plus `data.xlsx`. PPTX rendering uses the backend Node dependency `pptxgenjs`; run `npm install` in this directory after dependency updates. Chart slides export Plotly figures through Kaleido, which requires a local Chrome/Chromium-compatible runtime. Decks without chart slides do not require Kaleido image export at render time.

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
