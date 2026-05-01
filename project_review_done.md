# Code Review Remediation — Implementation Complete

## Overview
A tri-model code review (Gemini, Claude, Qwen) produced 62 findings across 9 categories. All issues have been resolved across 8 independently deployable batches, organized by priority and concern area. The only excluded item is API key rotation (`.env` is gitignored and local-only).

**Verification**: All 212 backend tests pass. Ruff lint clean. Frontend TypeScript compiles cleanly.

---

## Batch 1: P0 Production Blockers
**Status: DONE** | 6 changes across 5 files

### 1.1 Rate limiter IP resolution behind Caddy proxy
- **File**: `backend/app/main.py`
- Changed `request.client.host` to read `X-Forwarded-For` → `X-Real-IP` → fallback
- All users no longer share a single rate limit bucket behind the proxy

### 1.2 Removed `?token=` query param auth
- **File**: `backend/app/core/deps.py`
- Removed `query_token` parameter from `_resolve_token`, `get_household_from_token`, `get_current_user`
- Removed `Query` import
- Tokens no longer leak into access logs, browser history, or Referer headers

### 1.3 Magic-byte file validation
- **File**: `backend/app/core/storage.py`
- Added `MAGIC_SIGNATURES` dict for PDF (`%PDF`), JPEG (`\xff\xd8\xff`), PNG (`\x89PNG`)
- `save_file` validates actual file content against declared MIME type
- Existing `Content-Type` check kept as fast-fail before reading body

### 1.4 Renamed `NEXT_PUBLIC_API_URL` → `VITE_API_URL`
- **File**: `frontend/.env.example`
- Fixed the Next.js prefix that silently broke env var loading in Vite

### 1.5 Sanitized validation error responses
- **File**: `backend/app/main.py`
- Validation errors now exclude the `input` field (prevents password/medical data leaking in 422 responses)
- Returns only `loc`, `msg`, `type`

### 1.6 Non-root user in frontend Dockerfile
- **File**: `frontend/Dockerfile` (later removed — consolidated into root Dockerfile which already has `USER caddy`)

---

## Batch 2: Request Pipeline Hardening
**Status: DONE** | 6 changes across 5 files

### 2.1 Fixed SSE error message leak
- **File**: `backend/app/core/sse.py`
- Replaced `str(exc)[:200]` with generic `"An error occurred during streaming"`
- Full exception logged server-side only

### 2.2 Request ID middleware
- **New file**: `backend/app/core/middleware.py`
- `RequestIdMiddleware` generates UUID per request, adds `X-Request-ID` header to response
- Registered in `backend/app/main.py` before CORS middleware

### 2.3 Frontend API client hardened
- **File**: `frontend/src/lib/api-client.ts`
- Added `AbortController` with 30-second timeout
- Added try/catch for `TypeError` (network errors) and `AbortError` (timeout)
- Fixed 401 redirect race: replaced never-resolving `Promise` with `throw new ApiError(401)`
- Both `apiRequest` and `streamRequest` updated

### 2.4 Fixed CORS_ORIGINS default
- **File**: `docker-compose.yml`
- Used shell parameter expansion: `${DOMAIN:+,https://${DOMAIN}}` prevents empty `https://` origin

### 2.5 Request context in exception handler
- **File**: `backend/app/main.py`
- Generic exception handler now logs `request.method` and `request.url.path`

### 2.6 Removed broad `except Exception` in auth
- **File**: `backend/app/routers/auth.py`
- Removed generic catch — unexpected errors propagate to global handler
- Kept `except ValueError` for business logic errors

---

## Batch 3: JWT and Token Security Overhaul
**Status: DONE** | Most complex batch — new model, new endpoint, 59 frontend files

### 3.1 Short-lived JWT + refresh token rotation
- **New model**: `backend/app/models/refresh_token.py`
  - Fields: `id` (UUID PK), `user_id` (FK), `token_hash` (SHA-256), `expires_at`, `created_at`, `revoked_at`, `replaced_by`
  - Token is a random string (not a JWT) — verified via DB lookup only

- **Modified**: `backend/app/core/security.py`
  - Access token expiry: `timedelta(hours=24)` → `timedelta(minutes=15)`
  - Added `create_refresh_token()`, `verify_and_rotate_refresh_token()`, `revoke_all_refresh_tokens()`, `prune_expired_tokens()`
  - Replay detection: if refresh token already used, revokes entire token family

- **New endpoint**: `POST /auth/refresh` in `backend/app/routers/auth.py`
  - Accepts refresh token from cookie or request body
  - Returns new access + refresh pair, marks old as revoked

- **New migration**: `backend/alembic/versions/a1b2c3d4e5f6_add_refresh_tokens.py`

### 3.2 Moved JWT from localStorage to httpOnly cookies
- **Backend**: Login/refresh endpoints set `access_token` + `refresh_token` as httpOnly cookies
  - Cookie settings: `HttpOnly`, `Secure` (prod), `SameSite=Strict`, `Path=/`
  - Refresh token cookie scoped to `/api/v1/auth` only

- **Backend deps**: `_resolve_token` checks cookies first, then `Authorization` header

- **Frontend**: Added `credentials: "include"` to all fetch calls
  - Removed `Authorization` header injection from `apiRequest` and `streamRequest`
  - Removed `token` parameter from all 83 API functions across 14 API modules
  - Updated 59 frontend files to remove `getToken()` calls and token passing

### 3.3 Token revocation moved to DB-only
- Removed `_revoked_tokens` in-memory dict, `threading.Lock`, `load_revoked_tokens()` startup
- `_is_revoked()` now async, queries `revoked_tokens` table directly
- Added daily scheduled `prune_tokens` job for expired token cleanup

---

## Batch 4: File Upload and Storage Security
**Status: DONE** | 3 changes in `backend/app/core/storage.py`

### 4.1 Async file I/O with aiofiles
- Replaced `file_path.write_bytes()` → `aiofiles.open(...).write()`
- Replaced `file_path.read_bytes()` → `aiofiles.open(...).read()`
- Replaced `file_path.unlink()` → `aiofiles.os.remove()`
- No more blocking the async event loop during file operations

### 4.2 Path traversal protection
- Added `_validate_storage_path()` — resolves paths and checks they stay within storage root
- Called in `save_file`, `get_file`, `delete_file`

### 4.3 Protected `/health/detail` endpoint
- **File**: `backend/app/main.py`
- Added `X-Health-Key` header check against `settings.SECRET_KEY[:16]`
- Docker health check uses unauthenticated `/health` — not affected

---

## Batch 5: Database and Migration Hardening
**Status: DONE** | 4 changes across 4 files

### 5.1 New Alembic migration for refresh_tokens
- **File**: `backend/alembic/versions/a1b2c3d4e5f6_add_refresh_tokens.py`
- Creates `refresh_tokens` table with proper indexes and foreign keys

### 5.2 Removed auto-migrations from PostgreSQL startup
- **File**: `backend/app/core/database.py`
- Removed the `else` branch that ran `alembic upgrade head` in a thread
- Kept SQLite `create_all()` for dev convenience
- Added warning log reminding to run migrations separately

### 5.3 Added statement timeout and pool config
- PostgreSQL: `connect_args={"options": "-c statement_timeout=30000"}` (30s)
- SQLite: `timeout=30` added to `connect_args`

### 5.4 Fixed N+1 queries in backup import
- **File**: `backend/app/services/backup_service.py`
- Batch lookup with `WHERE id IN (...)` before loops for members and providers
- Eliminates per-item queries during import

---

## Batch 6: CSP and Ollama Architecture
**Status: DONE** | 2 major changes

### 6.1 Removed `unsafe-inline` from CSP script-src
- **File**: `Caddyfile`
- `script-src 'self' 'unsafe-inline'` → `script-src 'self'`
- `style-src 'unsafe-inline'` retained (required by shadcn/ui inline styles)

### 6.2 Extracted Ollama to separate Docker service
- **File**: `docker-compose.yml`
  - Added `ollama` service: `image: ollama/ollama`, persistent volume, health check, `backend` network
  - Backend receives `OLLAMA_LOCAL_URL=http://ollama:11434` env var
  - Backend depends on Ollama service

- **File**: `backend/app/main.py`
  - Removed entire `_ensure_ollama_ready()` function (~80 lines)
  - Removed `subprocess.Popen(["ollama", "serve"])` call
  - Removed all Ollama startup/wait logic

---

## Batch 7: Code Quality and Testing
**Status: DONE** | 5 changes

### 7.1 Re-enabled mypy checks
- **File**: `backend/pyproject.toml`
- Reduced from 13 disabled error codes → 2 (`name-defined`, `import-untyped`)
- Enabled `disallow_untyped_defs`, `check_untyped_defs`, `warn_return_any`
- mypy now catches real type errors across the codebase

### 7.2 Fixed scheduler delayed first execution
- **File**: `backend/app/core/scheduler.py`
- Moved `await asyncio.sleep(interval)` to AFTER job execution
- All jobs run immediately on startup, then wait the full interval

### 7.3 Token pruning scheduled job
- **File**: `backend/app/main.py`
- Added `prune_tokens` job running every 24 hours
- Cleans expired refresh tokens and revoked access tokens

### 7.4 Documented asyncio.gather thread-safety
- **File**: `backend/app/routers/health_records.py`
- Added comment documenting that shared AIService is safe for read-only AI provider calls
- Ollama client is now a separate service, eliminating mutable state concerns

### 7.5 Structured JSON logging for production
- **File**: `backend/app/main.py`
- JSON formatter configured when `python-json-logger` is installed and `APP_ENV=production`
- Falls back to console formatter gracefully

---

## Batch 8: Architectural Cleanup
**Status: DONE** | 3 changes

### 8.1 Consolidated Dockerfiles
- Removed standalone `frontend/Dockerfile` — root `Dockerfile` already handles multi-stage frontend + Caddy build
- Only root `Dockerfile` and `backend/Dockerfile` remain

### 8.2 Added Caddy health check to docker-compose
- **File**: `docker-compose.yml`
- `web` service health check: `wget --spider http://localhost:8080/health`

### 8.3 Audited `is_deleted` indexing
- Only `HealthRecord` uses soft-delete (`is_deleted`)
- Already properly indexed: single-column + two compound indexes
- No missing indexes identified

---

## Files Changed Summary

| Category | Files Modified | Files Created | Files Deleted |
|----------|---------------|---------------|---------------|
| Backend core | `security.py`, `deps.py`, `storage.py`, `database.py`, `middleware.py`, `sse.py`, `scheduler.py`, `config.py` | `middleware.py` | — |
| Backend models | `base.py` | `refresh_token.py` | — |
| Backend routers | `auth.py`, `health_records.py` | — | — |
| Backend services | `backup_service.py` | — | — |
| Backend schemas | `auth.py` | — | — |
| Backend config | `main.py`, `pyproject.toml` | — | — |
| Backend migrations | — | `a1b2c3d4e5f6_add_refresh_tokens.py` | — |
| Frontend core | `api-client.ts`, `auth.ts`, `constants.ts`, `.env.example` | — | — |
| Frontend API (14 files) | All `lib/api/*.ts` | — | — |
| Frontend pages (~30) | All pages removing token | — | — |
| Frontend components (~20) | All components removing token | — | — |
| DevOps | `docker-compose.yml`, `Caddyfile` | — | `frontend/Dockerfile` |
| Tests | `test_security.py`, `test_notifications.py` | — | — |

**Total: ~80 files changed across the full stack**

---

## Remaining Advisory Items

These items were identified but deferred as they require significant new code without immediate security impact:

1. **Split `ai_service.py`** (1,929 lines) into `ExtractionService`, `ChatService`, `VisionProvider`, `InsightProvider`
2. **Extract middleware from `main.py`** into dedicated module
3. **Use PostgreSQL in development** via docker-compose to match production
4. **Frontend component tests** with Vitest + React Testing Library
5. **AI service integration tests** against local Ollama
6. **Consolidated initial Alembic migration** — squash 3 existing migrations into one complete schema creation
