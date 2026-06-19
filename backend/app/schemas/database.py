"""Schemas for the database integrity check + repair feature (Data tab)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Maintenance operations exposed in the Data tab. SQLite uses the native
# PRAGMA/REINDEX/VACUUM semantics; PostgreSQL maps each to its portable
# equivalent (see app.services.db_maintenance).
RepairOperation = Literal["checkpoint", "reindex", "vacuum"]


class RepairRequest(BaseModel):
    operation: RepairOperation = Field(..., description="checkpoint | reindex | vacuum")


class TableCount(BaseModel):
    name: str
    count: int
    error: str | None = None  # set when the table could not be read (e.g. corruption)


class DatabaseStats(BaseModel):
    """Engine-specific storage stats. SQLite populates the PRAGMA fields;
    PostgreSQL only the size fields. Missing fields are ``None``."""

    engine: Literal["sqlite", "postgresql"]
    database_bytes: int = 0
    wal_bytes: int | None = None
    shm_bytes: int | None = None
    page_size: int | None = None
    page_count: int | None = None
    freelist_pages: int | None = None
    journal_mode: str | None = None


class IntegrityReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool  # structural integrity only (integrity_check + quick_check); FK excluded
    engine: Literal["sqlite", "postgresql"]
    integrity_check: list[str] = []  # PRAGMA integrity_check rows (["ok"] when healthy)
    quick_check: list[str] = []
    # Foreign-key violations are INFORMATIONAL: FK enforcement is intentionally
    # off on SQLite (see app/core/database.py) and the legacy UUID-format
    # mismatch guarantees spurious rows. Excluded from `ok`.
    foreign_key_violations: int = 0
    foreign_key_note: str | None = None
    tables: list[TableCount] = []
    stats: DatabaseStats
    duration_ms: int = 0
    timed_out: bool = False
    notes: list[str] = []


class _StatsSnapshot(BaseModel):
    """Before/after view used by repair responses to show reclamation."""

    database_bytes: int = 0
    freelist_pages: int | None = None
    wal_bytes: int | None = None


class RepairResponse(BaseModel):
    ok: bool
    operation: RepairOperation
    message: str = ""
    before: _StatsSnapshot | None = None
    after: _StatsSnapshot | None = None
    duration_ms: int = 0
    notes: list[str] = []
