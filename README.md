# Targeted File Review Assistant

Scaffold for a Targeted File Review application with:

- `backend`: uv-managed FastAPI API, Pydantic audit contracts, and Pydantic-AI agent factories.
- `frontend`: Next.js app shell with shadcn-style components, Tailwind light/dark mode, dashboard tables, form catalog, evaluation workflow, and persistent dockable chat.

## Backend

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

The current implementation uses starter data and intentionally thin service layers so the audit schema, persistence layer, CopilotKit AG-UI transport, and GEPA optimization workflow can evolve incrementally.
