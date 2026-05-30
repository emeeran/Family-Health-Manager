"""Main FastAPI application entry point."""
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import logging
import logging.config
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
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
    providers,
    provider_assignments,
    health_records,
    attachments,
    ai,
    conversations,
    reminders,
    notifications,
    audit,
    backup,
    dashboard,
    medications,
    vaccinations,
    smart_entry,
    smart_search,
    health_alerts,
    export,
    reports,
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
    "root": {"level": "INFO", "handlers": ["stdout"]},
}

settings = get_settings()

# Initialize Sentry if DSN configured
if settings.SENTRY_DSN:
    from app.core.sentry import init_sentry
    init_sentry(settings.SENTRY_DSN, environment=settings.APP_ENV)

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

    # Register background jobs
    register_job("process_reminders", 60, _jobs.process_reminders)
    register_job("rotate_backups", 86400, _jobs.rotate_backups)
    register_job("check_ai_providers", 300, _jobs.check_ai_providers)
    register_job("detect_anomalies", 21600, _jobs.detect_anomalies)

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

    # Database backup job
    register_job("backup_database", 86400, _jobs.backup_database)

    # Only start scheduler in designated container
    if settings.RUN_SCHEDULER:
        await start_scheduler()
    else:
        logger.info("Scheduler disabled (RUN_SCHEDULER=false)")

    logger.info("Application startup complete!")
    yield
    # Shutdown
    await stop_scheduler()
    from app.core.redis import close_redis
    await close_redis()
    from app.core.database import engine
    await engine.dispose()
    logger.info("Shutting down application...")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
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
auth_rate_limiter = RateLimiter(limit=10, window_seconds=60)  # Stricter for auth


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting and request size middleware."""
    # Reject oversized payloads (50MB max)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 50 * 1024 * 1024:
                return JSONResponse(
                    status_code=413,
                    content={"status_code": 413, "error": "payload_too_large", "message": "Request body exceeds 50MB limit"},
                )
        except (ValueError, TypeError):
            pass

    # Skip rate limiting for health checks and non-API routes
    if request.url.path in ("/health", "/health/detail", "/") or not request.url.path.startswith("/api"):
        return await call_next(request)

    # Resolve real client IP from proxy headers (Caddy sets X-Forwarded-For)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.headers.get("x-real-ip"):
        client_ip = request.headers.get("x-real-ip", "").strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    # Stricter rate limit for auth endpoints
    if request.url.path.startswith("/api/v1/auth/login") or request.url.path.startswith("/api/v1/auth/register"):
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
        details.append({
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        })
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
        request.method, request.url.path, exc, exc_info=True,
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
app.include_router(providers.router, prefix="/api/v1")
app.include_router(provider_assignments.router, prefix="/api/v1")
app.include_router(health_records.router, prefix="/api/v1")
app.include_router(attachments.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(reminders.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(backup.router, prefix="/api/v1")
app.include_router(medications.router, prefix="/api/v1")
app.include_router(vaccinations.router, prefix="/api/v1")
app.include_router(smart_entry.router, prefix="/api/v1")
app.include_router(smart_search.router, prefix="/api/v1")
app.include_router(health_alerts.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(dashboard.risk_router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/detail")
async def health_detail(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Detailed health check with DB connectivity test (requires shared secret)."""
    health_key = request.headers.get("x-health-key")
    expected = settings.HEALTH_CHECK_SECRET or settings.SECRET_KEY[:16]
    if not health_key or health_key != expected:
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
                    "model": settings.OLLAMA_MODEL if _has_model else f"{settings.OLLAMA_MODEL} (not pulled)",
                    "available_models": _models,
                }
            else:
                checks["ollama"] = {"server": "error", "model": "unknown"}
    except Exception:
        checks["ollama"] = {"server": "not_running", "model": settings.OLLAMA_MODEL}

    overall = "ok" if checks.get("database") == "ok" else "degraded"
    return {"status": overall, "checks": checks}
