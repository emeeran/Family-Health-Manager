# Family Health Manager

Self-hosted family health record manager with AI-powered document extraction,
medication tracking, and conversational health Q&A.

## Quick Start

```bash
./dev.sh                       # Start backend + frontend dev servers
cd backend && uv run pytest    # Run backend tests
cd frontend && npm test        # Run frontend tests (vitest)
```

`dev.sh` picks the next free port from `:8000` (backend) and `:3000` (frontend)
and sources `backend/.env` for secrets. The Vite dev proxy forwards `/api` to
the backend, so no CORS config is needed in dev.

## Tech Stack

| Layer     | Technology                              |
|-----------|-----------------------------------------|
| Frontend  | React 19, Vite, SWR, shadcn/ui          |
| Backend   | Python 3.11+, FastAPI, Pydantic v2      |
| Database  | SQLite (dev) / PostgreSQL (prod)        |
| Packaging | `uv` (Python) · Debian `.deb` (deploy)  |
| Testing   | pytest, httpx · vitest                  |
| Linting   | ruff, mypy · eslint, tsc                |

## Project Layout

| Path          | Contents                                                |
|---------------|---------------------------------------------------------|
| `backend/`    | FastAPI app, ORM models, services, tests                |
| `frontend/`   | React/Vite SPA                                          |
| `docs/`       | SDD artefacts (domain, requirements, spec, design)      |
| `prompts/`    | Prompt templates for the AI extraction pipeline         |
| `packaging/`  | Debian package, Caddyfile, systemd unit, deploy scripts |
| `scripts/`    | Deploy & sync helper scripts (gitignored)               |

## SDD Pipeline

The Makefile drives spec-driven-development phases; artefacts land in `docs/`.

| Phase | Command            | Output                                  |
|-------|--------------------|-----------------------------------------|
| 0     | `make domain`      | `docs/00-domain/DOMAIN.md`              |
| 1     | `make reqs`        | `docs/01-requirements/REQUIREMENTS.md`  |
| 2     | `make spec`        | `docs/02-spec/SPEC.md`                  |
| 3     | `make review`      | `docs/03-review/REVIEW.md` (gate)       |
| 4     | `make design`      | `docs/04-design/DESIGN.md`              |
| 5     | `make code`        | `backend/app/`                          |
| 5.5   | `make review-code` | Bloat report (auto-fix)                 |
| 6     | `make test`        | Test results + coverage                 |

Run `make help` for the full list of targets. See [CLAUDE.md](CLAUDE.md) for
engineering context and conventions.
