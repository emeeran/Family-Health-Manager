"""Database integrity check + maintenance (Data tab).

Read-only structural integrity scan plus admin-only repair operations
(checkpoint WAL / rebuild indexes / vacuum) for SQLite, with portable
PostgreSQL equivalents.

Safety notes
------------
* SQLite work runs on a *separate* ``sqlite3`` connection inside
  ``asyncio.to_thread`` — it never touches the async engine's connection
  pool. This generalises the ``_snapshot_sqlite`` precedent in
  ``app/core/jobs.py``.
* The repair connection uses ``isolation_level=None`` (autocommit): ``VACUUM``
  and ``REINDEX`` cannot run inside a transaction.
* ``busy_timeout=30000`` (longer than the engine's 5000 ms) lets a repair
  wait out an in-flight writer; a lingering lock still surfaces as a friendly
  "database is busy" result rather than an exception.
* Foreign-key violations are reported INFORMATIONALLY only and never affect
  the ``ok`` summary: FK enforcement is intentionally off on SQLite (see
  ``app/core/database.py``) and the legacy UUID-format mismatch guarantees
  spurious rows that are not corruption.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.models.base import Base
from app.schemas.database import (
    DatabaseStats,
    IntegrityReport,
    RepairOperation,
    RepairResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Serialise concurrent repairs (two VACUUMs at once just contend for the lock).
# Repair does not need the systemd delegation the restore flow uses, so an
# in-process lock is sufficient.
_REPAIR_LOCK = asyncio.Lock()
_INTEGRITY_TIMEOUT = 60  # seconds — integrity_check is a full scan

_FK_NOTE = (
    "Foreign-key checks are off by design on this SQLite install; a non-zero "
    "count reflects historical ID-format differences, not corruption."
)


def _is_sqlite() -> bool:
    return settings.DATABASE_URL.startswith("sqlite")


def _sqlite_db_path() -> Path:
    """Absolute path to the SQLite database file.

    Monkeypatch seam for tests (the test suite builds its own engine on a temp
    file rather than the configured URL).
    """
    raw = settings.DATABASE_URL.split(":///", 1)[-1]
    return Path(raw).resolve()


def _quote(ident: str) -> str:
    """Double-quote a SQL identifier, escaping embedded quotes."""
    return '"' + ident.replace('"', '""') + '"'


def _sidecar_size(path: Path, suffix: str) -> int:
    p = path.with_name(path.name + suffix)
    try:
        return p.stat().st_size if p.exists() else 0
    except OSError:
        return 0


# ── SQLite (sync — run in a worker thread) ───────────────────────────────────


def _sqlite_integrity_sync(path: Path) -> dict:
    """Read-only integrity scan. Opens a normal connection but issues no writes."""
    started = time.perf_counter()
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        integrity = [r[0] for r in conn.execute("PRAGMA integrity_check").fetchall()]
        quick = [r[0] for r in conn.execute("PRAGMA quick_check").fetchall()]
        fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())

        tables: list[dict] = []
        for name in Base.metadata.tables:
            try:
                count = conn.execute(f"SELECT count(*) FROM {_quote(name)}").fetchone()[0]
                tables.append({"name": name, "count": count, "error": None})
            except sqlite3.Error as exc:
                tables.append({"name": name, "count": 0, "error": str(exc)})

        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()

    db_bytes = path.stat().st_size if path.exists() else 0
    ok = integrity == ["ok"] and quick == ["ok"]
    notes: list[str] = []
    if not ok:
        notes.append("Structural integrity check reported problems — review the messages below.")
    if tables and any(t["error"] for t in tables):
        notes.append("One or more tables could not be read — they may be missing or corrupt.")

    return {
        "ok": ok,
        "engine": "sqlite",
        "integrity_check": integrity,
        "quick_check": quick,
        "foreign_key_violations": fk_violations,
        "foreign_key_note": _FK_NOTE if fk_violations else None,
        "tables": tables,
        "stats": DatabaseStats(
            engine="sqlite",
            database_bytes=db_bytes,
            wal_bytes=_sidecar_size(path, "-wal"),
            shm_bytes=_sidecar_size(path, "-shm"),
            page_size=page_size,
            page_count=page_count,
            freelist_pages=freelist,
            journal_mode=journal_mode,
        ),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "timed_out": False,
        "notes": notes,
    }


def _sqlite_snapshot(path: Path) -> dict:
    """Cheap before/after view for repair responses."""
    db_bytes = path.stat().st_size if path.exists() else 0
    freelist: int | None = None
    try:
        conn = sqlite3.connect(str(path), timeout=5)
        try:
            freelist = conn.execute("PRAGMA freelist_count").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return {
        "database_bytes": db_bytes,
        "freelist_pages": freelist,
        "wal_bytes": _sidecar_size(path, "-wal"),
    }


def _sqlite_repair_sync(path: Path, operation: RepairOperation) -> dict:
    started = time.perf_counter()
    before = _sqlite_snapshot(path)
    notes: list[str] = []
    message = ""
    ok = True

    try:
        # autocommit — VACUUM/REINDEX cannot run inside a transaction.
        conn = sqlite3.connect(str(path), isolation_level=None, timeout=30)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            if operation == "checkpoint":
                busy, log, checkpointed = conn.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                message = f"WAL checkpointed — {checkpointed} frame(s) merged, log now {log} frame(s)."
                if busy:
                    notes.append(
                        "Checkpoint was partial (a connection was active). "
                        "Retry when the app is idle to fully reclaim the WAL."
                    )
            elif operation == "reindex":
                conn.execute("REINDEX")
                message = "All indexes rebuilt."
            elif operation == "vacuum":
                conn.execute("VACUUM")
                message = "Database vacuumed and compacted."
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        # BUSY / LOCKED — another connection held the write lock.
        ok = False
        message = "Database is busy or locked — retry when the app is idle."
        notes.append(str(exc))
        logger.warning("SQLite repair '%s' blocked: %s", operation, exc)
    except sqlite3.DatabaseError as exc:
        ok = False
        message = f"Repair failed: {exc}"
        notes.append(str(exc))
        logger.warning("SQLite repair '%s' failed: %s", operation, exc)

    after = _sqlite_snapshot(path)
    return {
        "ok": ok,
        "operation": operation,
        "message": message,
        "before": before,
        "after": after,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "notes": notes,
    }


# ── PostgreSQL ───────────────────────────────────────────────────────────────


async def _pg_check_integrity() -> IntegrityReport:
    started = time.perf_counter()
    tables: list[dict] = []
    table_errors = 0
    db_bytes = 0
    try:
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            for name in Base.metadata.tables:
                try:
                    count = (
                        await conn.execute(text(f"SELECT count(*) FROM {_quote(name)}"))
                    ).scalar_one()
                    tables.append({"name": name, "count": count, "error": None})
                except Exception as exc:  # unreadable/missing table
                    table_errors += 1
                    tables.append({"name": name, "count": 0, "error": str(exc)})
            db_bytes = (
                await conn.execute(text("SELECT pg_database_size(current_database())"))
            ).scalar_one()
    except Exception:
        logger.exception("PostgreSQL integrity scan failed")

    return IntegrityReport(
        ok=table_errors == 0,
        engine="postgresql",
        tables=tables,
        stats=DatabaseStats(engine="postgresql", database_bytes=db_bytes or 0),
        duration_ms=int((time.perf_counter() - started) * 1000),
        notes=[
            "PostgreSQL enforces structural integrity server-side; this scan "
            "verifies every table is readable."
        ],
    )


async def _pg_snapshot() -> dict:
    try:
        async with engine.connect() as conn:
            size = (
                await conn.execute(text("SELECT pg_database_size(current_database())"))
            ).scalar_one()
        return {"database_bytes": size, "freelist_pages": None, "wal_bytes": None}
    except Exception:
        return {"database_bytes": 0, "freelist_pages": None, "wal_bytes": None}


async def _pg_repair(operation: RepairOperation) -> RepairResponse:
    started = time.perf_counter()
    before = await _pg_snapshot()
    notes: list[str] = []
    message = ""
    ok = True
    try:
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            if operation in ("checkpoint", "vacuum"):
                # checkpoint and vacuum both map to VACUUM (ANALYZE) on Postgres.
                await conn.execute(text("VACUUM (ANALYZE)"))
                message = "VACUUM ANALYZE complete — dead tuples reclaimed, planner stats refreshed."
            elif operation == "reindex":
                # REINDEX DATABASE needs superuser on managed Postgres; reindex
                # each app table concurrently instead (CONCURRENTLY = no exclusive lock).
                total = len(Base.metadata.tables)
                failed: list[str] = []
                for name in Base.metadata.tables:
                    try:
                        await conn.execute(text(f'REINDEX TABLE CONCURRENTLY {_quote(name)}'))
                    except Exception as exc:  # noqa: BLE001 — collect, continue
                        failed.append(f"{name}: {exc}")
                if failed:
                    notes.append(f"{len(failed)} table(s) could not be reindexed.")
                    notes.extend(failed[:5])
                message = f"Reindexed {total - len(failed)}/{total} tables concurrently."
    except Exception as exc:  # noqa: BLE001
        ok = False
        message = f"Repair failed: {exc}"
        logger.warning("PostgreSQL repair '%s' failed: %s", operation, exc)

    after = await _pg_snapshot()
    return RepairResponse(
        ok=ok,
        operation=operation,
        message=message,
        before=before,
        after=after,
        duration_ms=int((time.perf_counter() - started) * 1000),
        notes=notes,
    )


# ── Public API ───────────────────────────────────────────────────────────────


async def check_integrity() -> IntegrityReport:
    """Run a read-only integrity scan. Safe for any authenticated user."""
    if _is_sqlite():
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(_sqlite_integrity_sync, _sqlite_db_path()),
                timeout=_INTEGRITY_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Integrity check timed out after %ds", _INTEGRITY_TIMEOUT)
            return IntegrityReport(
                ok=False,
                engine="sqlite",
                stats=DatabaseStats(engine="sqlite", database_bytes=0),
                timed_out=True,
                notes=[
                    f"The scan did not finish within {_INTEGRITY_TIMEOUT}s. "
                    "Run it again when the app is idle."
                ],
            )
        return IntegrityReport(**data)
    return await _pg_check_integrity()


async def repair(operation: RepairOperation) -> RepairResponse:
    """Run an admin-only maintenance operation. Serialised by ``_REPAIR_LOCK``."""
    async with _REPAIR_LOCK:
        if _is_sqlite():
            data = await asyncio.to_thread(_sqlite_repair_sync, _sqlite_db_path(), operation)
            return RepairResponse(**data)
        return await _pg_repair(operation)
