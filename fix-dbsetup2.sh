#!/bin/bash
# Restore db-setup.py with a no-op alembic upgrade
cat > /tmp/db-setup-fix.py << 'PYEOF'
"""Database setup script for the .deb package."""

import os
import sys

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
    sync_url = db_url.replace("sqlite+aiosqlite", "sqlite")
    engine = create_engine(sync_url)
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if existing_tables:
        print(f"SQLite database already has {len(existing_tables)} tables — skipping.")
        engine.dispose()
        return

    print("Fresh SQLite database — creating tables from models...")
    from app.models.base import Base
    Base.metadata.create_all(engine)
    print(f"Created {len(Base.metadata.tables)} tables.")
    engine.dispose()


def setup_postgresql(db_url: str) -> None:
    print("PostgreSQL detected — running alembic upgrade head...")
    from alembic import command
    from alembic.config import Config
    alembic_cfg = Config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic"))
    command.upgrade(alembic_cfg, "head")


if __name__ == "__main__":
    main()
PYEOF
sudo cp /tmp/db-setup-fix.py /opt/health-manager/backend/db-setup.py
sudo systemctl start health-manager
sleep 3
systemctl is-active health-manager
