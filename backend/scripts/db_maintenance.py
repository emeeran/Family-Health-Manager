"""Database maintenance CLI for DAWNSTAR Family Health Keeper.

Usage:
    python -m scripts.db_maintenance <command>
    python scripts/db_maintenance.py <command>

Commands:
    vacuum          Run SQLite VACUUM to reclaim space and optimize
    stats           Print row counts for every table
    purge-deleted   Hard-delete soft-deleted health records
    clean-orphans   Remove records with dangling foreign keys
    backup          Copy the database to data/backups/ with rotation
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the backend/ root is on sys.path so `app.*` imports resolve
# regardless of how the script is invoked.
# ---------------------------------------------------------------------------
_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import create_engine, func, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.base import (  # noqa: E402
    AIInsight,
    Attachment,
    AuditLog,
    Conversation,
    FamilyMember,
    HealthRecord,
    Household,
    Message,
    Notification,
    Provider,
    ProviderAssignment,
    Reminder,
    User,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# All models in canonical order for the stats command.
_ALL_MODELS = [
    User,
    Household,
    FamilyMember,
    Provider,
    ProviderAssignment,
    HealthRecord,
    Attachment,
    AIInsight,
    Conversation,
    Message,
    Reminder,
    Notification,
    AuditLog,
]


def _get_db_file_path() -> str:
    """Return the filesystem path to the SQLite database file.

    Handles both ``sqlite+aiosqlite:///./data/health.db`` and
    ``sqlite:///./data/health.db`` URL forms, stripping the async driver
    suffix and the ``///`` prefix.
    """
    url: str = get_settings().DATABASE_URL
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return url[len(prefix):]
    raise ValueError(f"Unsupported DATABASE_URL scheme: {url}")


def _make_sync_engine():
    """Create a *synchronous* SQLAlchemy engine for CLI maintenance tasks."""
    db_path = _get_db_file_path()
    sync_url = f"sqlite:///{db_path}"
    return create_engine(sync_url, echo=False)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_vacuum() -> None:
    """Run SQLite VACUUM outside of any transaction wrapper.

    SQLAlchemy always wraps statements in a transaction, and VACUUM is one
    of the few SQLite commands that cannot run inside one.  We therefore
    use the stdlib ``sqlite3`` module directly.
    """
    db_path = _get_db_file_path()
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        sys.exit(1)

    size_before = os.path.getsize(db_path)
    print(f"Database : {db_path}")
    print(f"Size before: {size_before / 1024:.1f} KB")

    conn = sqlite3.connect(db_path)
    conn.execute("VACUUM")
    conn.close()

    size_after = os.path.getsize(db_path)
    print(f"Size after : {size_after / 1024:.1f} KB")
    reclaimed = size_before - size_after
    if reclaimed > 0:
        print(f"Reclaimed  : {reclaimed / 1024:.1f} KB")
    else:
        print("Reclaimed  : 0 KB (database was already compact)")


def cmd_stats() -> None:
    """Print row counts for every table."""
    engine = _make_sync_engine()
    with engine.connect() as conn:
        print(f"{'Table':<25} {'Rows':>8}")
        print("-" * 35)
        total = 0
        for model in _ALL_MODELS:
            count = conn.execute(
                select(func.count()).select_from(model)
            ).scalar_one()
            print(f"{model.__tablename__:<25} {count:>8}")
            total += count
        print("-" * 35)
        print(f"{'TOTAL':<25} {total:>8}")
    engine.dispose()


def cmd_purge_deleted() -> None:
    """Hard-delete health records where is_deleted=True."""
    engine = _make_sync_engine()
    with engine.begin() as conn:
        count_before = conn.execute(
            select(func.count()).select_from(HealthRecord)
        ).scalar_one()

        deleted_count = conn.execute(
            select(func.count()).select_from(HealthRecord).where(
                HealthRecord.is_deleted.is_(True)
            )
        ).scalar_one()

        if deleted_count == 0:
            print("No soft-deleted health records to purge.")
            engine.dispose()
            return

        conn.execute(
            HealthRecord.__table__.delete().where(
                HealthRecord.is_deleted.is_(True)
            )
        )

        count_after = conn.execute(
            select(func.count()).select_from(HealthRecord)
        ).scalar_one()

        print(f"Health records before purge: {count_before}")
        print(f"Soft-deleted records found : {deleted_count}")
        print(f"Health records after purge : {count_after}")
    engine.dispose()


def cmd_clean_orphans() -> None:
    """Remove records with dangling foreign-key references.

    1. Delete health_records whose family_member_id does not exist in
       family_members.
    2. Delete attachments whose health_record_id does not exist in
       health_records.
    """
    engine = _make_sync_engine()
    with engine.begin() as conn:
        # --- Orphan health_records (family_member_id) ---
        valid_member_ids = conn.execute(
            select(FamilyMember.id)
        ).scalars().all()

        orphan_records_result = conn.execute(
            HealthRecord.__table__.delete().where(
                HealthRecord.family_member_id.notin_(valid_member_ids)
            )
        )
        orphan_records_count = orphan_records_result.rowcount

        # --- Orphan attachments (health_record_id) ---
        valid_record_ids = conn.execute(
            select(HealthRecord.id)
        ).scalars().all()

        orphan_attachments_result = conn.execute(
            Attachment.__table__.delete().where(
                Attachment.health_record_id.notin_(valid_record_ids)
            )
        )
        orphan_attachments_count = orphan_attachments_result.rowcount

        print(f"Orphan health_records deleted: {orphan_records_count}")
        print(f"Orphan attachments deleted   : {orphan_attachments_count}")
    engine.dispose()


def cmd_backup() -> None:
    """Copy the SQLite database to data/backups/ with timestamp.

    Keeps only the last 10 backups; older ones are deleted automatically.
    """
    db_path = _get_db_file_path()
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        sys.exit(1)

    # Resolve the backups directory relative to the project backend root.
    backup_dir = Path(_BACKEND_ROOT) / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"health_{timestamp}.db"
    backup_path = backup_dir / backup_name

    shutil.copy2(db_path, backup_path)
    size_kb = backup_path.stat().st_size / 1024
    print(f"Backup created: {backup_path} ({size_kb:.1f} KB)")

    # Rotate: keep only the 10 most recent backups.
    # Sort by filename (which encodes the timestamp) rather than mtime,
    # to avoid ambiguity when files are created within the same second.
    existing_backups = sorted(
        backup_dir.glob("health_*.db"),
        key=lambda p: p.name,
    )
    if len(existing_backups) > 10:
        to_delete = existing_backups[: len(existing_backups) - 10]
        for old_backup in to_delete:
            old_backup.unlink()
            print(f"Removed old backup: {old_backup.name}")

    remaining = list(backup_dir.glob("health_*.db"))
    print(f"Backups retained: {len(remaining)}/10")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

_COMMANDS = {
    "vacuum": cmd_vacuum,
    "stats": cmd_stats,
    "purge-deleted": cmd_purge_deleted,
    "clean-orphans": cmd_clean_orphans,
    "backup": cmd_backup,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DAWNSTAR Family Health Keeper — database maintenance utilities",
    )
    parser.add_argument(
        "command",
        choices=list(_COMMANDS.keys()),
        help="Maintenance command to run",
    )
    args = parser.parse_args()
    _COMMANDS[args.command]()


if __name__ == "__main__":
    main()
