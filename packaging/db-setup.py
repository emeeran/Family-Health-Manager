"""Database setup script for the .deb package.

For SQLite (fresh install):
  - Creates all tables from SQLAlchemy models
  - Stamps alembic at the latest revision (skips broken ALTER TABLE migrations)

For PostgreSQL:
  - Runs alembic upgrade head normally
"""

import os
import sys

# Ensure the backend directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, inspect

from app.core.config import get_settings


def main():
    settings = get_settings()
    db_url = settings.DATABASE_URL

    if db_url.startswith("sqlite"):
        setup_sqlite(db_url)
    else:
        setup_postgresql(db_url)


def setup_sqlite(db_url: str) -> None:
    """Create tables from models and stamp alembic for SQLite."""
    sync_url = db_url.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(sync_url)

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if existing_tables:
        print(f"SQLite database already has {len(existing_tables)} tables — skipping creation.")
        print("Running alembic upgrade head for any pending migrations...")
        _alembic_upgrade_head()
        return

    print("Fresh SQLite database — creating tables from models...")

    # Import all models so Base.metadata knows about them
    from app.models.base import Base  # noqa: F401 — triggers all model imports

    Base.metadata.create_all(engine)
    print(f"Created {len(Base.metadata.tables)} tables.")

    # Stamp alembic so it knows migrations are current
    _alembic_stamp_head()

    engine.dispose()


def setup_postgresql(db_url: str) -> None:
    """Run alembic migrations for PostgreSQL."""
    print("PostgreSQL detected — running alembic upgrade head...")
    _alembic_upgrade_head()


def _alembic_upgrade_head() -> None:
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic"))
    command.upgrade(alembic_cfg, "head")


def _alembic_stamp_head() -> None:
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic"))
    command.stamp(alembic_cfg, "head")
    print("Alembic stamped at head.")


if __name__ == "__main__":
    main()
