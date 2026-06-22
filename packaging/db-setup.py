"""Database setup script for the .deb package.

For SQLite (fresh install):
  - Creates all tables from SQLAlchemy models (fast path)
  - Stamps alembic at the latest revision

For SQLite (existing install) and PostgreSQL:
  - Runs alembic upgrade head (the baseline migration is runnable on both
    dialects; on a stamped DB this is a no-op).
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

    # Encrypt any legacy plaintext 2FA secrets (older installs stored
    # totp_secret / backup_codes unencrypted). Idempotent + best-effort.
    _encrypt_legacy_2fa_secrets(db_url)

    # Optimize + encrypt existing plaintext attachments (closes the at-rest
    # gap for files written before encryption was enabled). Idempotent +
    # best-effort. NOTE: PDF optimization is lossy — back up first.
    _migrate_attachments()


def _migrate_attachments() -> None:
    """Run the attachment encryption/optimization migration (best-effort)."""
    try:
        import asyncio
        from app.core.jobs import migrate_attachments_to_encrypted

        result = asyncio.run(migrate_attachments_to_encrypted())
        migrated = result.get("migrated", 0)
        failed = result.get("failed", 0)
        if migrated or failed:
            print(f"Attachment migration: {migrated} migrated, {failed} failed.")
    except Exception as exc:  # noqa: BLE001 — never block startup
        print(f"Attachment migration skipped: {exc}")


def _encrypt_legacy_2fa_secrets(db_url: str) -> None:
    """Encrypt plaintext totp_secret/backup_codes left over from older installs.

    Skips values that are already Fernet tokens. Wrapped so any failure logs
    but never blocks startup.
    """
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.models.base import User
        from app.core.encryption import encrypt_secret, is_secret_encrypted

        sync_url = db_url.replace("sqlite+aiosqlite", "sqlite").replace("+asyncpg", "")
        engine = create_engine(sync_url)
        changed = 0
        with Session(engine) as session:
            for u in session.execute(select(User)).scalars().all():
                touched = False
                if u.totp_secret and not is_secret_encrypted(u.totp_secret):
                    u.totp_secret = encrypt_secret(u.totp_secret)
                    touched = True
                if u.backup_codes and not is_secret_encrypted(u.backup_codes):
                    u.backup_codes = encrypt_secret(u.backup_codes)
                    touched = True
                if touched:
                    changed += 1
            if changed:
                session.commit()
        engine.dispose()
        if changed:
            print(f"Encrypted 2FA secrets at rest for {changed} user(s).")
    except Exception as exc:  # noqa: BLE001 — never block startup on this
        print(f"2FA-secret migration skipped: {exc}")


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
