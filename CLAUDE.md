# Family Health Manager — Claude Context

## Project Purpose
Self-hosted family health record manager with AI-powered document extraction, medication tracking, and conversational health Q&A.

## Tech Stack
| Layer     | Technology                          |
|-----------|-------------------------------------|
| Frontend  | React 19, Vite, SWR, shadcn/ui      |
| Backend   | Python 3.11+, FastAPI, Pydantic v2  |
| Database  | SQLite (dev) / PostgreSQL (prod)    |
| Packaging | `uv` (never use pip directly)       |
| Testing   | pytest, httpx, pytest-asyncio       |
| Linting   | ruff, mypy                          |
| OS        | Ubuntu 24.x                         |

## Key Commands
```bash
./dev.sh              # Start backend + frontend dev servers
cd backend && uv run pytest   # Run tests
cd backend && uv run ruff check --fix .  # Lint Python
```

## Project Structure
```
sdd-health-manager/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── core/            # Config, DB session, security
│   │   ├── routers/         # Route handlers
│   │   ├── models/          # ORM models
│   │   ├── schemas/         # Pydantic schemas
│   │   └── services/        # Business logic
│   ├── tests/
│   ├── .env                 # Local secrets (never commit)
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/             # Page components
│   │   ├── components/      # Shared UI components
│   │   ├── lib/             # API client, types, utilities
│   │   ├── layouts/         # App layout with sidebar
│   │   └── pages/           # Route-level page components
│   ├── vite.config.ts
│   └── package.json
├── docs/                    # SDD artefacts (domain, spec, design)
├── prompts/                 # Prompt templates for AI pipeline
├── automation/              # Audit reports and CI tooling
├── dev.sh                   # One-command dev server startup
├── docker-compose.yml
├── Dockerfile
├── Caddyfile
├── CLAUDE.md                # ← You are here
├── lefthook.yml             # Git hooks (lint, typecheck)
└── Makefile
```

## Conventions
- All secrets go in `backend/.env` — never hardcode.
- `uv add <pkg>` to add dependencies; `uv run pytest` to run tests.
- Frontend uses shadcn/ui components — check `src/components/ui/` before adding new ones.
- Vite dev proxy: `vite.config.ts` proxies `/api` to backend. No CORS needed in dev.
- Pre-commit: ruff lint + prettier format. Pre-push: mypy + tsc.
