# Deployment Guide

## Prerequisites

- Docker and Docker Compose
- A PostgreSQL database (provided via docker-compose)
- API keys for at least one AI provider (OpenAI, Gemini, Groq, or OpenRouter)

## Quick Start

```bash
# 1. Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with your SECRET_KEY and API keys

# 2. Generate a secure SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Paste the output into backend/.env as SECRET_KEY

# 3. Start services
docker compose up -d

# 4. Verify health
curl http://localhost:8080/health
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | YES | Random 32+ char string for JWT signing |
| `APP_ENV` | No | `development` (default) or `production` |
| `DATABASE_URL` | No | Auto-set in Docker; SQLite for local dev |
| `CORS_ORIGINS` | No | Comma-separated frontend URLs |
| `OPENAI_API_KEY` | No | OpenAI API key |
| `GEMINI_API_KEY` | No | Google Gemini API key |
| `GROQ_API_KEY` | No | Groq API key |
| `OPENROUTER_API_KEY` | No | OpenRouter API key |

**Production requirements** (`APP_ENV=production`):
- `SECRET_KEY` must be changed from the default
- `DEBUG` is forced to `false`
- OpenAPI docs are disabled

## Rollback Procedure

1. **Identify the issue**: Check `/health/detail` endpoint for DB/connectivity status
2. **Rollback Docker image**:
   ```bash
   # List recent images
   docker compose images backend
   # Rollback to previous version
   docker compose down
   docker tag sdd-health-manager-backend:<previous-sha> sdd-health-manager-backend:latest
   docker compose up -d
   ```
3. **Rollback database**: PostgreSQL backups are stored in `backups/` directory
   ```bash
   pg_restore -d healthmanager backups/pre-deploy-<timestamp>.dump
   ```
4. **Verify**: Check `/health` returns `{"status": "healthy"}`

## Health Checks

- `GET /health` — Basic health (no auth required)
- `GET /health/detail` — DB connectivity and disk usage (no auth required)

## Monitoring

- Docker health checks are configured with 30s intervals
- Application logs to stdout (structured JSON in production)
- Rate limiting: 100 req/min general, 10 req/min for auth endpoints

## Local Development

```bash
# Backend
cd backend
uv sync --dev
uv run uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Database Migrations

- **SQLite (dev)**: Tables are auto-created on startup
- **PostgreSQL (prod)**: Run Alembic migrations before deploy
  ```bash
  cd backend
  alembic upgrade head
  ```
