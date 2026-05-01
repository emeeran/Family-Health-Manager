<!-- AI Code Review Pipeline -->
<!-- Stack: unknown + react -->
<!-- Reports: 3/3 tools succeeded -->

# Code Review: Final Synthesis Report
## Project: Health Manager — React + Vite + TypeScript (SWR) | Python FastAPI | SQLite/PostgreSQL | Docker + Compose
## Date: 2026-05-01
## Reviewed by: Gemini CLI · Claude Code · Qwen Code

---

## Executive Summary

- **1 CRITICAL and 12 HIGH-severity findings** demand immediate attention before any production deployment. The most urgent is **plaintext API keys for four AI providers** present in the `.env` file.
- **Security posture is weak**: in-memory rate limiting and token revocation are ineffective behind reverse proxies and across replicas; JWTs are long-lived (24h) with no refresh mechanism and are exposed via query parameters and `localStorage`.
- **No meaningful backend test coverage exists**: critical authentication, CRUD, and AI service logic have zero automated regression protection, and CI test enforcement is absent.
- **Frontend environment configuration is broken**: uses `NEXT_PUBLIC_` prefix (Next.js convention) instead of `VITE_`, meaning the environment variable is silently ignored in the Vite build.
- **Positive findings**: multi-provider AI failover with racing is well-designed; backend Dockerfile uses multi-stage build with non-root user; Caddy security headers are present; `get_db()` dependency properly commits/rolls back; Docker internal network is correctly isolated.

---

## Critical & High Severity Issues

### 1. Plaintext API Keys Committed in `.env` | CRITICAL | `backend/.env`
[Confirmed by 2/3 reviewers — Claude, Qwen]

Live API keys for OpenAI, Gemini, Groq, and OpenRouter are hardcoded in plaintext. If this file is committed or leaked, all four provider accounts are compromised with significant financial exposure.

**Immediate actions:**
1. Rotate all four API keys now.
2. Verify no historical commits contain the file: `git log --all --full-history -- backend/.env`
3. Use Docker secrets or a secrets manager for production.

---

### 2. Token Revocation Uses In-Memory Dictionary | HIGH | `backend/app/core/security.py`
[Confirmed by 2/3 reviewers — Gemini, Claude]

`_revoked_tokens` is an in-memory dict with `threading.Lock`. It is not shared across workers, pods, or even process restarts. Combined with 24h token expiry and no refresh mechanism, a logged-out user's token remains valid on other replicas. Additionally, the `threading.Lock` can block the async event loop under contention.

**Fix:** Use Redis or database-backed blocklist. Replace `threading.Lock` with `asyncio.Lock`.

---

### 3. Rate Limiter Uses Direct TCP Peer IP — Ineffective Behind Proxy | HIGH | `backend/app/main.py:232`
[Unique: Claude]

`request.client.host` returns the proxy IP (e.g., `172.x.x.x`) behind Caddy, not the real client IP. All users share a single rate limit bucket, making protection useless.

**Fix:** Parse `X-Forwarded-For` header from Caddy with trusted-proxy validation:
```python
forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
client_ip = forwarded or (request.client.host if request.client else "unknown")
```

---

### 4. Ollama Daemon Spawned Inside API Container | HIGH | `backend/app/main.py:86-114`
[Confirmed by 2/3 reviewers — Gemini (HIGH), Claude (MEDIUM) → using HIGH]

`subprocess.Popen(["ollama", "serve"])` at startup violates containerization best practices. AI model execution can consume all container memory, crash the API pod, and drastically slow scaling. Also presents an arbitrary code execution risk if the `ollama` binary path is compromised.

**Fix:** Run Ollama as a separate Docker service in `docker-compose.yml` (like `db`). Remove all subprocess logic from `main.py`.

---

### 5. JWT Tokens Accepted via Query Parameter | HIGH | `backend/app/core/deps.py:39-45`
[Unique: Claude]

`?token=` query parameter fallback leaks session tokens into access logs, proxy logs, browser history, and Referer headers.

**Fix:** Remove query parameter token support entirely. If needed for SSE/file downloads, use short-lived one-time tokens.

---

### 6. MIME Validation Relies on Client-Provided Header | HIGH | `backend/app/core/storage.py:15`
[Unique: Claude]

`file.content_type` is trivially spoofable. An attacker can upload HTML with XSS payloads or SVG with embedded scripts by setting `Content-Type: image/jpeg`.

**Fix:** Validate file content with magic bytes (`python-magic` or `imghdr`) in addition to the header check.

---

### 7. 24-Hour JWT Expiry with No Refresh Tokens | HIGH | `backend/app/core/security.py:98`
[Unique: Claude]

Long-lived tokens mean a stolen token grants access for up to 24 hours. With in-memory revocation lost on restart, there is no way to force re-authentication.

**Fix:** Implement short-lived access tokens (15–30 min) with refresh token rotation.

---

### 8. JWT Stored in Browser `localStorage` | HIGH | `frontend/src/lib/auth.ts`
[Confirmed by 2/3 reviewers — Claude (MEDIUM), Qwen (HIGH) → using HIGH] [Severity escalated]

`localStorage` is accessible to any JavaScript on the page. Combined with `unsafe-inline` in CSP, any XSS vulnerability can steal session tokens.

**Fix:** Use `httpOnly` + `Secure` + `SameSite=Strict` cookies set by the backend.

---

### 9. MyPy Configuration Disables All Critical Checks | HIGH | `backend/pyproject.toml`
[Confirmed by 2/3 reviewers — Gemini (HIGH), Qwen (MEDIUM) → using HIGH] [Severity escalated]

20+ error codes disabled (including `no-untyped-def`, `arg-type`, `return-value`, `attr-defined`), defeating the purpose of static typing entirely.

**Fix:** Remove `disable_error_code` array. Gradually fix underlying type errors and enable stricter checks.

---

### 10. No Meaningful Backend Test Coverage | HIGH | `backend/tests/`
[Confirmed by 3/3 reviewers — Gemini (HIGH), Claude (MEDIUM), Qwen (MEDIUM) → using HIGH] [Severity escalated]

No API, integration, or robust unit tests exist for routers and services. No CI enforcement of test runs. AI service tests mock everything with no integration coverage. No frontend component tests.

**Fix:** Implement `pytest` + `httpx.AsyncClient` test suite covering auth, CRUD, and AI service endpoints. Add CI test gate with minimum coverage threshold.

---

### 11. Blocking File I/O in Async Context | HIGH | `backend/app/core/storage.py`
[Unique: Qwen]

`pathlib.Path.read_bytes()` and `write_bytes()` are synchronous calls that block the event loop during file operations, degrading concurrent request handling.

**Fix:** Use `aiofiles` for async file operations.

---

### 12. Incomplete Alembic Initial Migration | HIGH | `backend/alembic/versions/`
[Confirmed by 2/3 reviewers — Qwen (HIGH), Claude (MEDIUM) → using HIGH] [Severity escalated]

The initial migration only contains an enum alteration, not the full schema. Fresh deployments cannot create the complete database from migrations alone.

**Fix:** Generate a complete initial migration: `alembic revision --autogenerate -m "Initial schema - full database"`.

---

### 13. Docker Compose Loads Entire `.env` into Container | HIGH | `docker-compose.yml:25`
[Unique: Claude]

`env_file: ./backend/.env` exposes all secrets (including `SECRET_KEY`) as environment variables visible via `docker inspect`.

**Fix:** Use Docker secrets or a separate secrets file. Never load the development `.env` in production.

---

## Section Reviews

### 1. Security & Auth

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 1.1 | CRITICAL | Plaintext API keys in `.env` | `backend/.env` | Claude, Qwen |
| 1.2 | HIGH | In-memory token revocation not shared across replicas | `backend/app/core/security.py` | Gemini, Claude |
| 1.3 | HIGH | Rate limiter uses proxy IP, not real client IP | `backend/app/main.py:232` | Claude |
| 1.4 | HIGH | JWT accepted via `?token=` query param | `backend/app/core/deps.py:39` | Claude |
| 1.5 | HIGH | MIME validation trusts client `Content-Type` | `backend/app/core/storage.py:15` | Claude |
| 1.6 | HIGH | 24h JWT expiry with no refresh mechanism | `backend/app/core/security.py:98` | Claude |
| 1.7 | HIGH | JWT in `localStorage` vulnerable to XSS | `frontend/src/lib/auth.ts` | Claude, Qwen |
| 1.8 | MEDIUM | CSP allows `unsafe-inline` for scripts and styles | `Caddyfile:28` | Claude |
| 1.9 | MEDIUM | Request size check only validates `Content-Length` (bypassable via chunked encoding) | `backend/app/main.py:217` | Claude |
| 1.10 | MEDIUM | CORS origins parsed without HTTPS validation in production | `backend/app/main.py:153` | Qwen |
| 1.11 | LOW | `/health/detail` endpoint is unauthenticated, leaks infrastructure info | `backend/app/main.py:328` | Claude |

### 2. Architecture & API Design

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 2.1 | HIGH | Ollama spawned as subprocess inside API container | `backend/app/main.py:86` | Gemini, Claude |
| 2.2 | MEDIUM | AI service uses class-level mutable state unsafe under concurrency | `backend/app/services/ai_service.py:107` | Claude, Qwen |
| 2.3 | MEDIUM | Missing API versioning strategy at router level | `backend/app/main.py` | Qwen |
| 2.4 | MEDIUM | No request ID / correlation tracking across logs | `backend/app/main.py` | Claude, Qwen |
| 2.5 | MEDIUM | Background jobs run in same event loop as request handling | `backend/app/core/scheduler.py` | Qwen |
| 2.6 | LOW | Fire-and-forget insight tasks lost on server restart | `backend/app/routers/health_records.py:287` | Claude |
| 2.7 | LOW | `ai_service.py` is a 1930-line God class | `backend/app/services/ai_service.py` | Claude |

### 3. Database & ORM

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 3.1 | HIGH | Incomplete Alembic initial migration | `backend/alembic/versions/` | Qwen, Claude |
| 3.2 | MEDIUM | Auto-migrations on startup cause race conditions across replicas | `backend/app/core/database.py:52` | Gemini |
| 3.3 | MEDIUM | SQLite uses `create_all()` instead of Alembic migrations | `backend/app/core/database.py:57` | Claude |
| 3.4 | MEDIUM | `check_same_thread: False` disables SQLite thread safety | `backend/app/core/database.py:17` | Claude, Qwen |
| 3.5 | MEDIUM | SQLite in dev vs PostgreSQL in prod causes schema/behavior drift | `backend/app/core/config.py` | Qwen |
| 3.6 | MEDIUM | No statement timeout on database queries | `backend/app/core/database.py` | Qwen |
| 3.7 | LOW | Backup import has N+1 query pattern | `backend/app/services/backup_service.py:360` | Claude |
| 3.8 | LOW | No explicit pool configuration for SQLite | `backend/app/core/database.py` | Qwen |
| 3.9 | LOW | Soft-delete `is_deleted` column indexing is inconsistent across models | `backend/app/models/` | Qwen |

### 4. Async / Performance

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 4.1 | HIGH | Blocking synchronous file I/O in async context | `backend/app/core/storage.py` | Qwen |
| 4.2 | MEDIUM | `threading.Lock` used in async rate limiter blocks event loop | `backend/app/core/rate_limiter.py` | Claude |
| 4.3 | MEDIUM | In-memory rate limiter not shared across instances | `backend/app/core/rate_limiter.py` | Gemini, Qwen |
| 4.4 | MEDIUM | `asyncio.gather` shares mutable `AIService` state across concurrent coroutines | `backend/app/routers/health_records.py:143` | Claude |
| 4.5 | LOW | Background scheduler delays first execution by full interval | `backend/app/core/scheduler.py:25` | Claude |

### 5. Frontend & API Integration

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 5.1 | MEDIUM | `.env` uses `NEXT_PUBLIC_` prefix (Next.js) instead of `VITE_` | `frontend/.env.example`, `frontend/vite.config.ts` | Gemini, Claude, Qwen |
| 5.2 | MEDIUM | `fetch` wrapper doesn't catch network exceptions (DNS failure, unreachable) | `frontend/src/lib/api-client.ts:31` | Gemini |
| 5.3 | MEDIUM | Multiple 401 responses trigger redirect race; never-resolving Promise | `frontend/src/lib/api-client.ts:48` | Claude |
| 5.4 | MEDIUM | No request timeout on `fetch` calls | `frontend/src/lib/api-client.ts` | Claude |
| 5.5 | MEDIUM | SWR installed but no `useSWR` usage or cache invalidation found | `frontend/package.json` | Qwen |
| 5.6 | MEDIUM | No standardized error UI / global error boundary for API failures | `frontend/src/lib/api-client.ts` | Qwen |
| 5.7 | LOW | No request deduplication for concurrent identical API calls | `frontend/src/lib/api-client.ts` | Qwen |
| 5.8 | LOW | `API_BASE_URL` defaults to `/api/v1` — silently fails without Vite proxy | `frontend/src/lib/constants.ts` | Claude |

### 6. Error Handling & Logging

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 6.1 | MEDIUM | Validation errors return full `exc.errors()` including submitted passwords | `backend/app/main.py:192` | Gemini |
| 6.2 | MEDIUM | Generic `Exception` catch in auth registration hides infrastructure errors | `backend/app/routers/auth.py:33` | Claude |
| 6.3 | MEDIUM | SSE streams internal error details (`str(exc)[:200]`) to client | `backend/app/core/sse.py:46` | Claude |
| 6.4 | MEDIUM | Generic exception handler lacks request context (path, method) in logs | `backend/app/main.py:233` | Qwen |
| 6.5 | MEDIUM | File validation doesn't check for path traversal in filenames | `backend/app/core/storage.py:30` | Qwen |
| 6.6 | LOW | No structured/JSON logging for production log aggregation | `backend/app/main.py` | Qwen |

### 7. Code Quality & Typing

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 7.1 | HIGH | MyPy configuration disables all critical type checks | `backend/pyproject.toml` | Gemini, Qwen |
| 7.2 | MEDIUM | All models re-exported from `base.py` creates circular dependency risk | `backend/app/models/base.py` | Claude |
| 7.3 | LOW | Service methods lack return type annotations | `backend/app/services/` | Qwen |
| 7.4 | LOW | TypeScript strict mode on but no audit of `any` usage | `frontend/tsconfig.json` | Qwen |
| 7.5 | LOW | `main.py` is monolithic (280+ lines) with middleware, handlers, routers | `backend/app/main.py` | Qwen |

### 8. Testing Coverage

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 8.1 | HIGH | No backend API/integration/unit tests | `backend/tests/` | Gemini, Claude, Qwen |
| 8.2 | MEDIUM | AI service tests mock all external calls — no integration coverage | `backend/tests/unit/test_ai_service.py` | Qwen |
| 8.3 | MEDIUM | No frontend component tests | `frontend/src/components/` | Qwen |
| 8.4 | MEDIUM | No CI test runner configuration verified | GitHub Actions | Claude |
| 8.5 | LOW | No E2E test coverage metrics | `frontend/playwright.config.ts` | Qwen |

### 9. DevOps & Configuration

| # | Severity | Finding | Location | Confirmed By |
|---|----------|---------|----------|-------------|
| 9.1 | HIGH | `docker-compose.yml` loads entire `.env` with all secrets | `docker-compose.yml:25` | Claude |
| 9.2 | MEDIUM | `CORS_ORIGINS` defaults to empty string if `DOMAIN` is unset | `docker-compose.yml:27` | Claude |
| 9.3 | MEDIUM | Three Dockerfiles exist — confusing which to maintain | Root, `frontend/`, `backend/` | Claude |
| 9.4 | MEDIUM | No database health check for SQLite deployments | `docker-compose.yml` | Qwen |
| 9.5 | LOW | Frontend Caddy stage runs as root (no `USER` directive) | `frontend/Dockerfile` | Gemini, Claude |
| 9.6 | LOW | No `.dockerignore` in backend directory (includes `.venv`, `tests`) | `backend/` | Claude |
| 9.7 | LOW | No health check for Caddy/web service in docker-compose | `docker-compose.yml` | Claude |

---

## Tool-Exclusive Findings

### Only Gemini Flagged
| Severity | Finding | Location |
|----------|---------|----------|
| MEDIUM | `fetch` wrapper doesn't catch raw network exceptions | `frontend/src/lib/api-client.ts:31` |
| MEDIUM | Validation errors return full input payload including passwords | `backend/app/main.py:192` |

### Only Claude Flagged
| Severity | Finding | Location |
|----------|---------|----------|
| HIGH | JWT accepted via `?token=` query parameter | `backend/app/core/deps.py:39` |
| HIGH | Rate limiter uses proxy IP instead of real client IP | `backend/app/main.py:232` |
| HIGH | MIME type validation trusts spoofable `Content-Type` | `backend/app/core/storage.py:15` |
| HIGH | 24h JWT expiry with no refresh tokens | `backend/app/core/security.py:98` |
| HIGH | Docker Compose exposes all secrets as env vars | `docker-compose.yml:25` |
| MEDIUM | CSP allows `unsafe-inline` for scripts and styles | `Caddyfile:28` |
| MEDIUM | Request size check bypassable via chunked encoding | `backend/app/main.py:217` |
| MEDIUM | `asyncio.gather` shares mutable state across coroutines | `backend/app/routers/health_records.py:143` |
| MEDIUM | Multiple 401 responses trigger redirect race | `frontend/src/lib/api-client.ts:48` |
| MEDIUM | Generic `Exception` catch hides infrastructure errors | `backend/app/routers/auth.py:33` |
| MEDIUM | SSE leaks internal error details to client | `backend/app/core/sse.py:46` |
| MEDIUM | Models re-exported from `base.py` — circular dependency risk | `backend/app/models/base.py` |
| LOW | Fire-and-forget insight tasks lost on restart | `backend/app/routers/health_records.py:287` |
| LOW | `ai_service.py` is a 1930-line God class | `backend/app/services/ai_service.py` |
| LOW | N+1 query pattern in backup import | `backend/app/services/backup_service.py` |
| LOW | `/health/detail` endpoint is unauthenticated | `backend/app/main.py:328` |

### Only Qwen Flagged
| Severity | Finding | Location |
|----------|---------|----------|
| HIGH | Blocking file I/O (`pathlib`) in async context | `backend/app/core/storage.py` |
| MEDIUM | No statement timeout on database queries | `backend/app/core/database.py` |
| MEDIUM | Background jobs in same event loop — no error isolation | `backend/app/core/scheduler.py` |
| MEDIUM | SWR installed but never used — no cache invalidation | `frontend/package.json` |
| MEDIUM | No standardized error UI for API failures | `frontend/src/lib/api-client.ts` |
| MEDIUM | File validation doesn't prevent path traversal | `backend/app/core/storage.py:30` |
| MEDIUM | Generic exception handler lacks request context | `backend/app/main.py:233` |
| MEDIUM | CORS origins not validated for HTTPS in production | `backend/app/main.py:153` |
| LOW | No structured/JSON logging for production | `backend/app/main.py` |
| LOW | Service methods lack return type annotations | `backend/app/services/` |
| LOW | TypeScript `any` usage not audited | `frontend/tsconfig.json` |
| LOW | SQLite pool not explicitly configured | `backend/app/core/database.py` |
| LOW | Soft-delete column indexing inconsistent across models | `backend/app/models/` |

---

## Quick Wins
> Low-effort, high-impact fixes — ship these first

| # | Fix | Effort | Impact | Files |
|---|-----|--------|--------|-------|
| QW-1 | **Rename `NEXT_PUBLIC_API_URL` → `VITE_API_URL`** in `.env.example` and config | 5 min | All 3 reviewers flagged; silently broken today | `frontend/.env.example`, `frontend/vite.config.ts` |
| QW-2 | **Add `USER caddy`** to frontend Dockerfile server stage | 1 line | Removes root privilege in container | `frontend/Dockerfile` |
| QW-3 | **Sanitize validation errors** — remove `input` field before returning | 3 lines | Prevents password echo in API responses | `backend/app/main.py:192` |
| QW-4 | **Add try/catch around `fetch`** in api-client with structured `ApiError` | 5 lines | Prevents unhandled rejections on network failure | `frontend/src/lib/api-client.ts:31` |
| QW-5 | **Fix 401 redirect race** — add `isRedirecting` flag, reject promise | 5 lines | Prevents multiple simultaneous redirects | `frontend/src/lib/api-client.ts:48` |
| QW-6 | **Add `X-Forwarded-For` parsing** for rate limiter IP | 3 lines | Makes rate limiting actually functional behind Caddy | `backend/app/main.py:232` |
| QW-7 | **Run scheduler jobs immediately on first iteration**, then sleep | 2 lines | Eliminates up-to-6-hour delay for background jobs | `backend/app/core/scheduler.py:25` |
| QW-8 | **Add request ID middleware** (UUID per request, in logs + response header) | 10 lines | Enables request tracing across logs | `backend/app/main.py` |
| QW-9 | **Add `backend/.dockerignore`** excluding `.venv`, `tests`, `__pycache__` | 5 lines | Faster Docker builds, smaller context | New file |
| QW-10 | **Remove query-parameter JWT support** | 3 lines | Eliminates token leakage via logs/Referer | `backend/app/core/deps.py:39` |

---

## Recommended Action Plan

### P0 — This Sprint ( blockers before any production deploy )

- [ ] **Rotate all four API keys** in `backend/.env` immediately; verify no git history contains the file
- [ ] **Fix rate limiter IP resolution** to use `X-Forwarded-For` behind Caddy
- [ ] **Remove `?token=` query parameter** auth from `deps.py`
- [ ] **Add magic-byte file validation** to `storage.py` (in addition to `Content-Type`)
- [ ] **Rename `NEXT_PUBLIC_API_URL` → `VITE_API_URL`** across frontend config
- [ ] **Sanitize validation error responses** to strip `input` field
- [ ] **Add `USER caddy`** to frontend Dockerfile

### P1 — Next Sprint ( security hardening & reliability )

- [ ] **Implement short-lived JWT access tokens (15–30 min) with refresh token rotation**
- [ ] **Move token revocation to database or Redis** backed store
- [ ] **Extract Ollama to a separate Docker service**; remove subprocess from `main.py`
- [ ] **Move JWT storage from `localStorage` to httpOnly cookies**
- [ ] **Remove `unsafe-inline` from CSP**; implement nonce-based CSP with Vite
- [ ] **Replace blocking file I/O with `aiofiles`** in storage service
- [ ] **Generate complete Alembic initial migration** for fresh deployments
- [ ] **Remove auto-migrations from app startup**; use init container or CI step
- [ ] **Add `try/catch` + `AbortController` timeout** to frontend `fetch` wrapper
- [ ] **Add request ID middleware** for log correlation
- [ ] **Implement basic backend test suite** (auth + core CRUD) with CI enforcement

### P2 — Backlog ( architectural improvements )

- [ ] **Implement distributed rate limiting** (Redis-backed) for multi-replica deployments
- [ ] **Use PostgreSQL in development** via docker-compose to match production
- [ ] **Add statement timeout** to database engine configuration
- [ ] **Split `ai_service.py`** into `ExtractionService`, `ChatService`, `VisionProvider`
- [ ] **Extract middleware, exception handlers, router registration** from `main.py`
- [ ] **Add SWR hooks** with cache invalidation for data fetching
- [ ] **Add frontend component tests** (critical: auth forms, record display)
- [ ] **Add AI service integration tests** against local Ollama
- [ ] **Implement structured JSON logging** for production log aggregation
- [ ] **Add path traversal protection** in file upload filename handling
- [ ] **Fix `asyncio.gather` shared mutable state** in concurrent file extraction
- [ ] **Re-enable mypy checks** gradually; fix underlying type errors
- [ ] **Consolidate Dockerfiles** — remove unused `frontend/Dockerfile`
- [ ] **Add backend `.dockerignore`** and Caddy health check to docker-compose
- [ ] **Audit `is_deleted` indexing** across all models with soft-delete pattern

---

## Appendix: Severity Matrix

| Section | CRITICAL | HIGH | MEDIUM | LOW | INFO |
|---|:---:|:---:|:---:|:---:|:---:|
| 1. Security & Auth | 1 | 5 | 3 | 1 | 0 |
| 2. Architecture & API Design | 0 | 1 | 4 | 2 | 0 |
| 3. Database & ORM | 0 | 1 | 5 | 3 | 0 |
| 4. Async / Performance | 0 | 1 | 3 | 1 | 0 |
| 5. Frontend & API Integration | 0 | 0 | 6 | 2 | 0 |
| 6. Error Handling & Logging | 0 | 0 | 5 | 1 | 0 |
| 7. Code Quality & Typing | 0 | 1 | 1 | 3 | 0 |
| 8. Testing Coverage | 0 | 1 | 3 | 1 | 0 |
| 9. DevOps & Configuration | 0 | 1 | 3 | 3 | 0 |
| **Total** | **1** | **11** | **33** | **17** | **0** |

---

## Appendix: Agreement Matrix

| Finding | Gemini | Claude | Qwen |
|---|:---:|:---:|:---:|
| Plaintext API keys in `.env` | — | CRITICAL | CRITICAL |
| In-memory token revocation | HIGH | HIGH | — |
| Rate limiter uses wrong IP | — | HIGH | — |
| In-memory rate limiter not distributed | MEDIUM | — | MEDIUM |
| Ollama subprocess in API container | HIGH | MEDIUM | — |
| JWT via query parameter | — | HIGH | — |
| MIME type trusts client header | — | HIGH | — |
| 24h JWT expiry, no refresh | — | HIGH | — |
| JWT in `localStorage` | — | MEDIUM | HIGH |
| MyPy checks disabled | HIGH | — | MEDIUM |
| No backend test coverage | HIGH | MEDIUM | MEDIUM |
| Blocking file I/O | — | — | HIGH |
| Incomplete Alembic migration | — | MEDIUM | HIGH |
| Docker compose loads `.env` secrets | — | HIGH | — |
| `NEXT_PUBLIC_` vs `VITE_` prefix | MEDIUM | MEDIUM | MEDIUM |
| Auto-migrations race condition | MEDIUM | — | — |
| SQLite `create_all` vs Alembic | — | MEDIUM | — |
| AI service shared mutable state | — | MEDIUM | MEDIUM |
| SQLite thread safety disabled | — | MEDIUM | LOW |
| CORS origins not validated | — | — | MEDIUM |
| CORS empty string default | — | MEDIUM | — |
| No request ID tracking | — | LOW | MEDIUM |
| Caddy runs as root | LOW | LOW | — |
| Generic exception handler lacks context | — | — | MEDIUM |
| SSE leaks error details | — | MEDIUM | — |
| Validation errors leak input data | MEDIUM | — | — |
| `fetch` no network error handling | MEDIUM | — | — |
| CSP `unsafe-inline` | — | MEDIUM | — |
| Request size check bypass | — | MEDIUM | — |
| `asyncio.gather` shared state | — | MEDIUM | — |
| 401 redirect race | — | MEDIUM | — |
| Generic Exception catch in auth | — | MEDIUM | — |
| Models re-export from `base.py` | — | MEDIUM | — |
| Multiple Dockerfiles confusion | — | MEDIUM | — |
| Missing API versioning | — | — | MEDIUM |
| Background jobs in event loop | — | — | MEDIUM |
| SWR installed but unused | — | — | MEDIUM |
| No error UI components | — | — | MEDIUM |
| Path traversal in file upload | — | — | MEDIUM |
| No DB query timeout | — | — | MEDIUM |
| SQLite vs PostgreSQL dev/prod drift | — | — | MEDIUM |
| No DB healthcheck for SQLite | — | — | MEDIUM |
| `ai_service.py` God class (1930 lines) | — | LOW | — |
| Monolithic `main.py` | — | — | LOW |
| No structured logging | — | — | LOW |
| N+1 backup import | — | LOW | — |
| Scheduler delayed first run | — | LOW | — |
| No fetch timeout | — | LOW | — |
| Unauthenticated `/health/detail` | — | LOW | — |
| Fire-and-forget insight tasks | — | LOW | — |
| No backend `.dockerignore` | — | LOW | — |
| No Caddy health check | — | LOW | — |
| Soft delete index inconsistency | — | — | LOW |
| No request deduplication | — | — | LOW |
| No E2E coverage report | — | — | LOW |
| Service methods lack type hints | — | — | LOW |
| TypeScript `any` audit | — | — | LOW |
| SQLite pool not configured | — | — | LOW |

---

*Report generated 2026-05-01. Total findings: 62 unique issues across 3 independent reviews.*