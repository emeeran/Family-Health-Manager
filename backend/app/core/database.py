"""Database engine and session management."""
from collections.abc import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import get_settings

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
        "pool_size": 10,
        "max_overflow": 20,
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
        cursor.close()

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
    import logging
    from sqlalchemy import create_engine
    from app.models.base import Base  # Import here to ensure models are registered

    logger = logging.getLogger(__name__)
    logger.info("Ensuring database tables exist...")

    if settings.DATABASE_URL.startswith("sqlite"):
        # Fast path for SQLite dev: create_all handles missing tables
        sync_db_url = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "sqlite:///")
        sync_engine = create_engine(sync_db_url, echo=False)
        Base.metadata.create_all(sync_engine)

        # Patch: add columns that may be missing from prior schema versions
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
                    logger.info("Added 'role' column to users table")

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
                    logger.info("Added storage columns to attachments table")

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
                    logger.info("Added 'provider_type' column to providers table")

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
                    logger.info("Added 'settings_json' column to households table")

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
                    logger.info("Added 'summary' column to health_records table")

        sync_engine.dispose()
    else:
        # Production: migrations should be run separately
        logger.info(
            "PostgreSQL detected — ensure migrations are run before startup "
            "(use: alembic upgrade head)"
        )

    logger.info("Database tables ready!")


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
