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

## Local app launch on EC2

From the repo root on the instance, run both the API and Next.js dev server with:

```bash
bash scripts/dev.sh
```

The helper checks required commands, verifies the default ports are free, applies Alembic
migrations, sets `NEXT_PUBLIC_API_BASE_URL` for the frontend process, and stops both dev
servers on Ctrl+C. Use `bash scripts/dev.sh --install` the first time to sync/install local
dependencies. For SSH forwarding, tunnel both ports:

```bash
ssh -L 3000:127.0.0.1:3000 -L 8000:127.0.0.1:8000 ec2-user@<ec2-public-dns-or-ip>
```

By default it binds to `127.0.0.1`, which is the safer choice for SSH port forwarding. To expose
the dev servers through an EC2 public DNS name or IP, open the relevant security group ports and
run:

```bash
bash scripts/dev.sh --host 0.0.0.0 --public-host <ec2-public-dns-or-ip>
```

`--public-host` sets the frontend's browser-facing API URL and adds a matching backend CORS
origin for the dev process. Useful options include `--backend-port 8001`, `--frontend-port 3001`,
`--with-postgres`, and `--skip-migrations`.

The current implementation uses starter data and intentionally thin service layers so the audit schema, persistence layer, CopilotKit AG-UI transport, and GEPA optimization workflow can evolve incrementally.
