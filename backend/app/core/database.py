"""Database engine and session management."""

import logging
import time
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def get_async_connection_url(db_url: str) -> str:
    """Convert SQLite URL to async aiosqlite URL."""
    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    return db_url


connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)
pool_kwargs = {}
if not settings.DATABASE_URL.startswith("sqlite"):
    pool_kwargs = {
        # Performance optimization (#9): increased pool for higher concurrency under load
        "pool_size": 25,
        "max_overflow": 50,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "connect_args": {"options": "-c statement_timeout=30000"},
    }

engine = create_async_engine(
    get_async_connection_url(settings.DATABASE_URL),
    echo=False,
    connect_args=connect_args,
    **pool_kwargs,
)

# Enable WAL mode for SQLite — allows concurrent reads during writes
if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        # Wait (ms) on a locked DB instead of failing immediately — guards
        # against transient "database is locked" under concurrent writes. 30s
        # (not 5s): under `uvicorn --workers 2`, batch extraction + record saves
        # + background summary/insight tasks write concurrently; 5s was too short
        # and surfaced as recurring OperationalError "database is locked".
        cursor.execute("PRAGMA busy_timeout=30000")
        # NOTE: PRAGMA foreign_keys=ON is intentionally NOT set. Existing
        # databases were created/populated with FK enforcement off, and the
        # schema stores UUIDs inconsistently (users.id as 32-char hex via the
        # Uuid type; child FK columns like refresh_tokens.user_id as dashed
        # VARCHAR(36)), so enforcing FKs now would reject otherwise-valid
        # writes (e.g. login's refresh-token insert) and break existing
        # installs. Postgres enforces FKs natively regardless.
        cursor.close()


# ---------------------------------------------------------------------------
# Performance optimization (#19): slow query logging
# Logs any query that takes longer than 500ms at WARNING level.
# Only enabled in non-test environments to avoid noise during test runs.
# ---------------------------------------------------------------------------
_SLOW_QUERY_THRESHOLD_MS = 500
_is_test_env = settings.APP_ENV == "test"


if not _is_test_env:

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("_query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start_time = conn.info.get("_query_start_time", [None])
        if start_time:
            elapsed_ms = (time.perf_counter() - start_time.pop()) * 1000
            if elapsed_ms > _SLOW_QUERY_THRESHOLD_MS:
                # Truncate long statements to keep log lines readable
                stmt_preview = statement[:300] + "..." if len(statement) > 300 else statement
                logger.warning(
                    "Slow query detected (%.0fms): %s",
                    elapsed_ms,
                    stmt_preview,
                )


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def create_tables():
    """Create/update database tables.

    SQLite (dev): run ``alembic upgrade head`` so dev databases share one schema
    source with production (the squashed baseline create_all + migrations).
    PostgreSQL (prod): migrations are run separately (``alembic upgrade head``)
    — never auto-applied on startup, where a long/locking migration could stall boot.
    """
    import logging as _logging

    _logger = _logging.getLogger(__name__)
    _logger.info("Ensuring database tables exist...")

    if settings.DATABASE_URL.startswith("sqlite"):
        # Dev convenience: bring the SQLite database to the current schema via
        # Alembic — the squashed baseline (create_all) plus incremental
        # migrations. This replaces the old runtime ALTER-TABLE patch block:
        # those same column additions now live in migration m9n0o1p2q3r4, so dev
        # and prod share one schema source (closes TODO #21). All migrations are
        # idempotent (existence-guarded), so this is safe on a fresh, old, or
        # already-current database.
        from pathlib import Path

        from alembic import command
        from alembic.config import Config

        alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        command.upgrade(Config(str(alembic_ini)), "head")
    else:
        # Production: migrations should be run separately
        _logger.info(
            "PostgreSQL detected — ensure migrations are run before startup "
            "(use: alembic upgrade head)"
        )

    _logger.info("Database tables ready!")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency providing database session."""
    db = SessionLocal()
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()


async def update_model(
    db: AsyncSession, model: object, allowed_fields: set[str] | None = None, **kwargs
) -> object:
    """Update model fields from kwargs and flush. Supports setting fields to None.

    If allowed_fields is provided, only those fields will be updated.
    """
    for key, value in kwargs.items():
        if allowed_fields is not None and key not in allowed_fields:
            continue
        if hasattr(model, key):
            setattr(model, key, value)
    await db.flush()
    return model
