"""Main FastAPI application entry point."""

import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import logging
import logging.config
import secrets
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.core.database import create_tables
from app.core.middleware import RequestIdMiddleware
from app.core.rate_limiter import RateLimiter
from app.core.scheduler import register_job, start_scheduler, stop_scheduler
from app.core import jobs as _jobs
from app.models import base  # noqa: F401 — Import models to register with Base.metadata
from app.models import revoked_token  # noqa: F401 — Register RevokedToken table
from app.models import refresh_token  # noqa: F401 — Register RefreshToken table
from app.routers import (
    auth,
    household,
    members,
    member_history,
    member_insights,
    member_preconsultation,
    member_smart_report,
    member_medication_report,
    member_drug_interactions,
    member_drug_info,
    member_resources,
    member_preventive,
    providers,
    provider_assignments,
    health_records,
    attachments,
    ai,
    conversations,
    reminders,
    notifications,
    backup,
    dashboard,
    medications,
    vaccinations,
    smart_entry,
    smart_search,
    health_alerts,
    database,
    system,
)

logger = logging.getLogger(__name__)

# Configure root logger so all app-level loggers emit output
_config: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {"level": "WARNING", "handlers": ["stdout"]},
    "loggers": {
        "sqlalchemy.engine": {"level": "WARNING"},
        "app.core.scheduler": {"level": "ERROR"},
        "app.core.jobs": {"level": "ERROR"},
    },
}

settings = get_settings()

# Apply the configured root log level (validated; falls back to WARNING on a typo
# so a bad LOG_LEVEL can't crash startup).
_log_level = settings.LOG_LEVEL.upper()
if _log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    _log_level = "WARNING"
_config["root"]["level"] = _log_level

# Use JSON logging in production if python-json-logger is available
if settings.APP_ENV == "production":
    try:
        import pythonjsonlogger.jsonformatter  # noqa: F401

        _config["formatters"]["json"] = {
            "class": "pythonjsonlogger.jsonformatter.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
        _config["handlers"]["stdout"]["formatter"] = "json"
    except ImportError:
        pass

logging.config.dictConfig(_config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting up application...")
    await create_tables()

    # Register background jobs. Heavy jobs are individually togglable and
    # retimable (see REMINDERS_ENABLED / *_INTERVAL in config) so a low-resource
    # host can shed work it doesn't need. Defaults preserve the original cadence.
    if settings.REMINDERS_ENABLED:
        register_job("process_reminders", settings.REMINDER_POLL_INTERVAL, _jobs.process_reminders)
    register_job("rotate_backups", 86400, _jobs.rotate_backups)
    if settings.AI_PROVIDER_HEALTH_CHECK_ENABLED:
        register_job("check_ai_providers", settings.AI_HEALTH_CHECK_INTERVAL, _jobs.check_ai_providers)
    if settings.ANOMALY_DETECTION_ENABLED:
        register_job("detect_anomalies", settings.ANOMALY_DETECTION_INTERVAL, _jobs.detect_anomalies)
    register_job("cleanup_staging", 3600, _jobs.cleanup_staging_files)
    if settings.FILE_INTEGRITY_CHECK_ENABLED:
        register_job(
            "verify_file_integrity", settings.FILE_INTEGRITY_CHECK_INTERVAL, _jobs.verify_file_integrity
        )

    # Sweep orphaned staging files from crashed sessions
    from app.core.storage import sweep_orphaned_staging

    await sweep_orphaned_staging()

    # Ensure Ollama is running + models pulled, and warm the model — all
    # NON-BLOCKING. ensure_ollama_ready() can wait up to 30s for the server and
    # up to ~10min if a model must be pulled; running it in the foreground
    # stalled app startup on a cold box. AI paths already degrade gracefully
    # when Ollama isn't ready yet (cloud fallback / friendly error), so boot the
    # app immediately and do readiness + warmup in the background.
    from app.core.ollama_service import ensure_ollama_ready

    async def _ollama_boot():
        try:
            if await ensure_ollama_ready():
                logger.info("Ollama ready — primary AI provider: %s", settings.OLLAMA_MODEL)
                # Warm the model into memory so the first user extraction skips
                # the ~9-20s CPU cold-load. A failure just cold-loads on demand.
                if settings.OLLAMA_WARMUP_ON_STARTUP:
                    from app.core.ollama_service import warmup_model

                    for mdl in {settings.OLLAMA_MODEL, settings.OLLAMA_TEXT_MODEL}:
                        if mdl:
                            await warmup_model(mdl)
            else:
                logger.warning(
                    "Ollama not available — will fall back to cloud providers if configured"
                )
        except Exception as exc:  # never let a boot task crash the event loop
            logger.warning("Ollama startup check failed: %s", exc)

    asyncio.create_task(_ollama_boot())

    # Auto-tune cloud AI models to the latest economical-capable on boot —
    # refreshes each provider's catalog and sets the best model in every
    # household (prevents stale/retired-model 404s). NON-BLOCKING + wrapped so a
    # dead provider or a failed fetch can never stall or crash startup.
    if settings.AI_AUTOTUNE_MODELS_ON_STARTUP:

        async def _autotune_models():
            try:
                from app.core.database import SessionLocal
                from app.services.ai.model_autoselect import refresh_and_autoselect

                async with SessionLocal() as db:
                    chosen = await refresh_and_autoselect(db)
                    await db.commit()
                if chosen:
                    logger.info(
                        "Model auto-tune: %s",
                        ", ".join(f"{k}={v}" for k, v in chosen.items()),
                    )
            except Exception as exc:  # never let a boot task crash the event loop
                logger.warning("Model auto-tune failed: %s", exc)

        asyncio.create_task(_autotune_models())

    # Token pruning — clean up expired refresh and revoked tokens daily
    async def _prune_tokens():
        from app.core.database import SessionLocal
        from app.core.security import prune_expired_tokens

        async with SessionLocal() as db:
            count = await prune_expired_tokens(db)
            await db.commit()
            if count:
                logger.info("Pruned %d expired tokens", count)

    register_job("prune_tokens", 86400, _prune_tokens)

    # Database backup job — ticks hourly; the job self-gates on the household's
    # configured backup_schedule (off/daily/weekly) so cadence is live-editable.
    register_job("backup_database", 3600, _jobs.backup_database)

    # Only start scheduler in designated container
    if settings.RUN_SCHEDULER:
        await start_scheduler()
    else:
        logger.info("Scheduler disabled (RUN_SCHEDULER=false)")

    logger.info("Application startup complete!")
    yield
    # Shutdown
    # Let in-flight scheduled jobs finish (bounded) before tearing down the DB
    # engine — without this, engine.dispose() can pull the connection pool out
    # from under a running backup/anomaly job. A 30s ceiling keeps a stuck job
    # from hanging shutdown; the atomic backup ensures a force-kill leaves no
    # corrupt archive regardless.
    try:
        await asyncio.wait_for(stop_scheduler(), timeout=30)
    except asyncio.TimeoutError:
        logger.warning("Scheduler shutdown timed out after 30s — proceeding")
    from app.core.redis import close_redis

    await close_redis()
    from app.core.database import engine

    await engine.dispose()
    logger.info("Shutting down application...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Self-hosted, privacy-first family health record manager with AI-powered "
        "document extraction, medication tracking, and conversational health Q&A. "
        "Local-first via Ollama with optional cloud provider fallbacks."
    ),
    contact={"name": "Family Health Manager"},
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
    lifespan=lifespan,
    docs_url=None if settings.APP_ENV == "production" else "/docs",
    redoc_url=None if settings.APP_ENV == "production" else "/redoc",
    openapi_url=None if settings.APP_ENV == "production" else "/openapi.json",
)

# GZip compression for responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Request ID tracking
app.add_middleware(RequestIdMiddleware)

# CORS middleware
origins = settings.CORS_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Rate limiter
rate_limiter = RateLimiter(
    limit=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW,
)
auth_rate_limiter = RateLimiter(
    limit=settings.AUTH_RATE_LIMIT_REQUESTS,
    window_seconds=settings.AUTH_RATE_LIMIT_WINDOW,
)  # Stricter for auth (override AUTH_RATE_LIMIT_REQUESTS for local E2E)


# Performance optimization (#22): set of paths and prefixes that never need rate limiting.
# Using a frozenset for O(1) membership checks and a tuple of prefixes for startswith checks.
_RATE_LIMIT_SKIP_PATHS = frozenset(
    {
        "/health",
        "/health/detail",
        "/",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)
_RATE_LIMIT_SKIP_PREFIXES = ("/static/", "/assets/", "/favicon")


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting and request size middleware."""
    # Performance: skip all header parsing and rate checks for non-API paths.
    # This avoids unnecessary content-length parsing, IP resolution, and rate
    # limit lookups for health checks, docs, and static assets.
    path = request.url.path
    if (
        path in _RATE_LIMIT_SKIP_PATHS
        or path.startswith(_RATE_LIMIT_SKIP_PREFIXES)
        or not path.startswith("/api")
    ):
        return await call_next(request)

    # Reject oversized payloads. Limits are tiered by path and configurable via
    # env (see MAX_REQUEST_SIZE_MB / MAX_UPLOAD_SIZE_MB / MAX_BACKUP_SIZE_MB in
    # config): general API JSON stays small, file uploads (extract, attachments)
    # get a larger cap so scanned-PDF batches aren't rejected, backup restore the
    # largest.
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if path.startswith("/api/v1/backup"):
                limit = settings.MAX_BACKUP_SIZE_MB * 1024 * 1024
            elif path.startswith("/api/v1/attachments") or "/records/extract" in path:
                limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            else:
                limit = settings.MAX_REQUEST_SIZE_MB * 1024 * 1024
            if int(content_length) > limit:
                return JSONResponse(
                    status_code=413,
                    content={
                        "status_code": 413,
                        "error": "payload_too_large",
                        "message": f"Request body exceeds {limit // (1024 * 1024)}MB limit",
                    },
                )
        except (ValueError, TypeError):
            pass

    # Resolve real client IP from proxy headers (Caddy sets X-Forwarded-For)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.headers.get("x-real-ip"):
        client_ip = request.headers.get("x-real-ip", "").strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    # Stricter rate limit for auth endpoints — covers ALL credential entrypoints
    # (login, register, login/2fa, change-password, 2fa/setup|verify|disable,
    # refresh) so a 6-digit TOTP or password can't be brute-forced at the generic
    # 100/min ceiling. /auth/me (GET, not a credential target, called on app
    # load) keeps the general limit.
    if path.startswith("/api/v1/auth/") and not path.startswith("/api/v1/auth/me"):
        allowed, retry_after = await auth_rate_limiter.check_limit_async(f"auth:{client_ip}")
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "status_code": 429,
                    "error": "rate_limit_exceeded",
                    "message": "Too many authentication attempts. Please try again later.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

    allowed, retry_after = await rate_limiter.check_limit_async(f"ip:{client_ip}")

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "status_code": 429,
                "error": "rate_limit_exceeded",
                "message": "Rate limit exceeded. Please try again later.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    response = await call_next(request)
    return response


# Global exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Return structured JSON for request validation errors."""
    # Strip the 'input' field to avoid leaking sensitive data (passwords, etc.)
    details = []
    for error in exc.errors():
        details.append(
            {
                "loc": error.get("loc", []),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "status_code": 422,
            "error": "validation_error",
            "message": "Request validation failed",
            "details": details,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "status_code": 500,
            "error": "internal_error",
            "message": "An unexpected error occurred",
        },
    )


# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(household.router, prefix="/api/v1")
app.include_router(members.router, prefix="/api/v1")
app.include_router(member_history.router, prefix="/api/v1")
app.include_router(member_insights.router, prefix="/api/v1")
app.include_router(member_preconsultation.router, prefix="/api/v1")
app.include_router(member_smart_report.router, prefix="/api/v1")
app.include_router(member_medication_report.router, prefix="/api/v1")
app.include_router(member_drug_interactions.router, prefix="/api/v1")
app.include_router(member_drug_info.router, prefix="/api/v1")
app.include_router(member_resources.router, prefix="/api/v1")
app.include_router(member_preventive.router, prefix="/api/v1")
app.include_router(providers.router, prefix="/api/v1")
app.include_router(provider_assignments.router, prefix="/api/v1")
app.include_router(health_records.router, prefix="/api/v1")
app.include_router(attachments.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(reminders.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(backup.router, prefix="/api/v1")
app.include_router(medications.router, prefix="/api/v1")
app.include_router(vaccinations.router, prefix="/api/v1")
app.include_router(smart_entry.router, prefix="/api/v1")
app.include_router(smart_search.router, prefix="/api/v1")
app.include_router(health_alerts.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(dashboard.risk_router, prefix="/api/v1")
app.include_router(database.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    """Readiness probe: the process is up AND the database answers.

    Unauthenticated (a cheap SELECT 1, no sensitive data) so external uptime
    monitors and systemd can use it; returns 503 when the DB is unreachable so a
    load balancer stops routing traffic. /health (liveness) stays dependency-free
    so it stays green during a transient DB blip; /health/detail is the
    authenticated deep check (disk + Ollama too).
    """
    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
        return JSONResponse(status_code=200, content={"status": "ready"})
    except Exception:
        logger.warning("Readiness check: database connectivity failed")
        return JSONResponse(status_code=503, content={"status": "not_ready"})


@app.get("/health/detail")
async def health_detail(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Detailed health check with DB connectivity test (requires shared secret)."""
    health_key = request.headers.get("x-health-key") or ""
    expected = settings.HEALTH_CHECK_SECRET
    if not expected:
        # Dev-only fallback. Production enforces HEALTH_CHECK_SECRET in config,
        # so SECRET_KEY is never reachable here in prod.
        expected = settings.SECRET_KEY[:16]
    if not secrets.compare_digest(health_key, expected):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    import shutil

    checks = {}
    # DB check
    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.warning("Health check: database connectivity failed")
        checks["database"] = "error"

    # Disk check
    try:
        usage = shutil.disk_usage(".")
        checks["disk"] = {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
        }
    except Exception:
        logger.warning("Health check: disk usage failed", exc_info=True)
        checks["disk"] = "unknown"

    # Ollama check
    try:
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=5) as _client:
            _resp = await _client.get(f"{settings.OLLAMA_LOCAL_URL}/api/tags")
            if _resp.status_code == 200:
                _models = [m["name"] for m in _resp.json().get("models", [])]
                _has_model = any(settings.OLLAMA_MODEL in m for m in _models)
                checks["ollama"] = {
                    "server": "ok",
                    "model": settings.OLLAMA_MODEL
                    if _has_model
                    else f"{settings.OLLAMA_MODEL} (not pulled)",
                    "available_models": _models,
                }
            else:
                checks["ollama"] = {"server": "error", "model": "unknown"}
    except Exception:
        checks["ollama"] = {"server": "not_running", "model": settings.OLLAMA_MODEL}

    overall = "ok" if checks.get("database") == "ok" else "degraded"
    # Surface degradation as 503 so load balancers / systemd notice and don't
    # route traffic to an unhealthy instance. A reachable-but-degraded app still
    # returns the full body for operators inspecting the response.
    status_code = 200 if overall == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks},
    )


# ── Desktop mode: serve the built SPA from the backend (same-origin) ──────────
# Enabled only when SERVE_FRONTEND is set (the Tauri desktop sidecar turns it on
# via env). The server .deb keeps using Caddy, so this never mounts there.
# Registered LAST so every /api/v1/* router and /health* route above takes
# precedence; the catch-all only handles client-side SPA routing + static files.
if settings.SERVE_FRONTEND:
    import sys as _sys
    from pathlib import Path as _Path

    from fastapi import HTTPException as _HTTPException
    from fastapi.responses import FileResponse as _FileResponse
    from fastapi.staticfiles import StaticFiles as _StaticFiles

    # Frozen (PyInstaller): the dist is bundled under sys._MEIPASS/frontend.
    # Unfrozen: use FRONTEND_DIST (e.g. `python desktop_main.py` from backend/).
    _meipass = getattr(_sys, "_MEIPASS", None)
    if _meipass:
        _fe_root = (_Path(_meipass) / "frontend").resolve()
    elif settings.FRONTEND_DIST:
        _fe_root = _Path(settings.FRONTEND_DIST).resolve()
    else:
        _fe_root = None
    if _fe_root and (_fe_root / "index.html").is_file():
        # Hashed Vite assets live under /assets/* (immutable). Other top-level
        # static files (favicon, manifest, runtime-config.js) are served by the
        # catch-all below.
        _fe_assets = _fe_root / "assets"
        if _fe_assets.is_dir():
            app.mount("/assets", _StaticFiles(directory=_fe_assets), name="frontend-assets")

        @app.get("/{full_path:path}")
        async def _spa_fallback(full_path: str):
            # Never shadow the API/health routes — an unmatched /api or /health
            # path should 404 as JSON, not return the SPA shell.
            if full_path.startswith(("api/", "health")):
                raise _HTTPException(status_code=404)
            candidate = (_fe_root / full_path).resolve()
            # Serve a real static file if present and contained within the dist
            # (guards against ../ traversal); otherwise fall back to index.html
            # so react-router deep links (/login, /members/123, ...) resolve.
            if candidate.is_file() and candidate.is_relative_to(_fe_root):
                return _FileResponse(candidate)
            return _FileResponse(_fe_root / "index.html")
