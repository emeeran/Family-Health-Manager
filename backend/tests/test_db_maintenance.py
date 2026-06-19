"""Tests for the database integrity check + repair endpoints.

The service reads the SQLite file directly via a separate connection, so these
tests point it at a temp DB (monkeypatching the path seam) populated with the
full schema — mirroring how ``test_backup_restore.py`` patches ``jobs`` paths.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.models.base import Base

OPS = ["checkpoint", "reindex", "vacuum"]


def _seed_sqlite(path: Path) -> None:
    """Create the full schema on a temp SQLite file."""
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    eng.dispose()


def _point_service_at(monkeypatch, path: Path) -> None:
    monkeypatch.setattr("app.services.db_maintenance._sqlite_db_path", lambda: path)


async def _non_admin_token(client) -> str:
    """Register + log in a second (non-admin) user."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "regular", "password": "TestP@ss123"},
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "regular", "password": "TestP@ss123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_integrity_requires_auth(client):
    """No token → 401."""
    resp = await client.get("/api/v1/database/integrity")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_integrity_report_healthy(auth_client, tmp_path, monkeypatch):
    """On a fresh, schema-complete SQLite DB the report is healthy (ok=True)."""
    db = tmp_path / "health.db"
    _seed_sqlite(db)
    _point_service_at(monkeypatch, db)

    resp = await auth_client.get("/api/v1/database/integrity")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["engine"] == "sqlite"
    assert body["integrity_check"] == ["ok"]
    assert body["quick_check"] == ["ok"]
    # Every registered table is present with a count.
    names = {t["name"] for t in body["tables"]}
    assert {"users", "households"}.issubset(names)
    assert all(t["error"] is None for t in body["tables"])
    assert body["timed_out"] is False
    assert body["stats"]["page_count"] > 0
    assert body["stats"]["journal_mode"] in {"delete", "wal", "memory", "truncate", "persist"}


@pytest.mark.asyncio
async def test_integrity_flags_missing_table(auth_client, tmp_path, monkeypatch):
    """A table in metadata but absent from the file shows up as an error, not a crash."""
    db = tmp_path / "health.db"
    _seed_sqlite(db)
    _point_service_at(monkeypatch, db)
    # Drop one table out from under the scan.
    with create_engine(f"sqlite:///{db}").connect() as conn:
        conn.exec_driver_sql("DROP TABLE users")
        conn.commit()

    resp = await auth_client.get("/api/v1/database/integrity")
    assert resp.status_code == 200
    body = resp.json()
    users = next(t for t in body["tables"] if t["name"] == "users")
    assert users["error"] is not None
    # integrity_check itself still passes (the file is structurally fine; a table is just missing).
    assert body["integrity_check"] == ["ok"]


@pytest.mark.asyncio
async def test_repair_requires_admin(auth_client, tmp_path, monkeypatch):
    """Non-admin users get 403 even on a valid request."""
    db = tmp_path / "health.db"
    _seed_sqlite(db)
    _point_service_at(monkeypatch, db)
    token = await _non_admin_token(auth_client)

    resp = await auth_client.post(
        "/api/v1/database/repair",
        json={"operation": "reindex"},
        params={"token": token},  # override the admin token for this call
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_repair_conflict_when_restore_in_progress(auth_client, monkeypatch):
    """A pending restore yields 409 and the operation is not attempted."""
    monkeypatch.setattr("app.core.jobs.is_restore_in_progress", lambda: True)
    resp = await auth_client.post("/api/v1/database/repair", json={"operation": "vacuum"})
    assert resp.status_code == 409
    assert "restore is in progress" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_repair_rejects_bad_operation(auth_client):
    """Unknown operations are rejected by the schema (422)."""
    resp = await auth_client.post("/api/v1/database/repair", json={"operation": "defragment"})
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", OPS)
async def test_repair_operations_succeed(auth_client, tmp_path, monkeypatch, operation):
    """Each maintenance operation runs and returns before/after snapshots."""
    db = tmp_path / "health.db"
    _seed_sqlite(db)
    _point_service_at(monkeypatch, db)

    resp = await auth_client.post("/api/v1/database/repair", json={"operation": operation})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["operation"] == operation
    assert body["before"] is not None and body["after"] is not None
    assert body["duration_ms"] >= 0
    assert body["message"]  # human-readable outcome
