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


connect_args = {"check_same_thread": False, "timeout": 30} if settings.DATABASE_URL.startswith("sqlite") else {}
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
        # against transient "database is locked" under concurrent writes.
        cursor.execute("PRAGMA busy_timeout=5000")
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

    For SQLite (dev): uses create_all() for fast startup.
    For PostgreSQL (prod): should run `alembic upgrade head` separately.
    """
    import logging as _logging
    from sqlalchemy import create_engine
    from app.models.base import Base  # Import here to ensure models are registered

    _logger = _logging.getLogger(__name__)
    _logger.info("Ensuring database tables exist...")

    if settings.DATABASE_URL.startswith("sqlite"):
        # Fast path for SQLite dev: create_all handles missing tables
        sync_db_url = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "sqlite:///")
        sync_engine = create_engine(sync_db_url, echo=False)
        Base.metadata.create_all(sync_engine)

        # -----------------------------------------------------------------
        # SQLite-only runtime schema patching (development convenience)
        #
        # These ALTER TABLE statements patch columns that may be missing from
        # prior schema versions in the SQLite dev database. They exist solely
        # so developers can run the app against an older SQLite file without
        # manually running migrations.
        #
        # This block is NEVER executed against PostgreSQL — production uses
        # Alembic migrations (`alembic upgrade head`) managed separately.
        #
        # TODO (#21): Convert each block below into a proper Alembic migration
        # so that PostgreSQL production deployments are covered. Currently these
        # patches are SQLite-only dev convenience methods. When adding new
        # columns, prefer creating an Alembic migration first and only add a
        # fallback patch here if needed for the SQLite dev workflow.
        # -----------------------------------------------------------------
        import sqlalchemy.inspection as sa_inspect
        with sync_engine.connect() as conn:
            inspector = sa_inspect.inspect(sync_engine)
            if "users" in inspector.get_table_names():
                existing_cols = {c["name"] for c in inspector.get_columns("users")}
                if "role" not in existing_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                        )
                    )
                    # Promote first user to admin
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "UPDATE users SET role = 'admin' WHERE id = "
                            "(SELECT id FROM users ORDER BY created_at ASC LIMIT 1)"
                        )
                    )
                    conn.commit()
                    _logger.info("Added 'role' column to users table")

            # Attachment storage columns
            if "attachments" in inspector.get_table_names():
                att_cols = {c["name"] for c in inspector.get_columns("attachments")}
                if "content_hash" not in att_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE attachments ADD COLUMN content_hash VARCHAR(64)"
                        )
                    )
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "CREATE INDEX IF NOT EXISTS ix_attachments_content_hash "
                            "ON attachments (content_hash)"
                        )
                    )
                if "storage_backend" not in att_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE attachments ADD COLUMN storage_backend VARCHAR(20) "
                            "NOT NULL DEFAULT 'local'"
                        )
                    )
                if "thumbnail_path" not in att_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE attachments ADD COLUMN thumbnail_path VARCHAR(500)"
                        )
                    )
                if "encrypted" not in att_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE attachments ADD COLUMN encrypted BOOLEAN "
                            "NOT NULL DEFAULT 0"
                        )
                    )
                if "content_hash" not in att_cols or "storage_backend" not in att_cols:
                    conn.commit()
                    _logger.info("Added storage columns to attachments table")

            # Provider type column
            if "providers" in inspector.get_table_names():
                prov_cols = {c["name"] for c in inspector.get_columns("providers")}
                if "provider_type" not in prov_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE providers ADD COLUMN provider_type VARCHAR(20) "
                            "NOT NULL DEFAULT 'doctor'"
                        )
                    )
                    conn.commit()
                    _logger.info("Added 'provider_type' column to providers table")

            # Household settings column
            if "households" in inspector.get_table_names():
                hh_cols = {c["name"] for c in inspector.get_columns("households")}
                if "settings_json" not in hh_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE households ADD COLUMN settings_json TEXT"
                        )
                    )
                    conn.commit()
                    _logger.info("Added 'settings_json' column to households table")

            # Health record summary column
            if "health_records" in inspector.get_table_names():
                hr_cols = {c["name"] for c in inspector.get_columns("health_records")}
                if "summary" not in hr_cols:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "ALTER TABLE health_records ADD COLUMN summary TEXT"
                        )
                    )
                    conn.commit()
                    _logger.info("Added 'summary' column to health_records table")

        sync_engine.dispose()
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
