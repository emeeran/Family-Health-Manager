"""Database engine and session management."""
from collections.abc import AsyncGenerator
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
        sync_engine = create_engine(sync_db_url, echo=settings.DEBUG)
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

        sync_engine.dispose()
    else:
        # Production: migrations should be run separately (docker-entrypoint.sh handles this)
        logger.info(
            "PostgreSQL detected — ensure migrations are run before startup "
            "(docker-entrypoint.sh handles this automatically)"
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
