"""Tests for the disaster-recovery restore endpoints.

The privileged stop → swap → start is performed out-of-process by a systemd
unit, so these tests cover only the endpoint layer: admin gating, archive-name
validation, the pending-restore guard, and that a valid request writes the
archive name into the flag file the path-unit watches.
"""

from pathlib import Path

import pytest

VALID_NAME = "backup_20260101_000000.tar.gz"
RESTORE_PATH = f"/api/v1/backup/archives/{VALID_NAME}/restore"


async def _non_admin_token(client) -> str:
    """Register + log in a second user (the admin already exists via auth_client).

    The second registered user is auto-assigned role="user".
    """
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
async def test_restore_requires_admin(auth_client):
    """Non-admin users get 403."""
    token = await _non_admin_token(auth_client)
    resp = await auth_client.post(RESTORE_PATH, params={"token": token})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_restore_rejects_bad_archive_name(auth_client):
    """Names that don't match the strict archive regex are rejected before any work."""
    resp = await auth_client.post("/api/v1/backup/archives/not-an-archive/restore")
    assert resp.status_code == 400
    assert "Invalid archive name" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_restore_404_for_missing_archive(auth_client):
    """A well-formed name that doesn't exist on disk returns 404."""
    resp = await auth_client.post(RESTORE_PATH)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Archive not found"


@pytest.mark.asyncio
async def test_restore_queued_writes_flag_file(auth_client, monkeypatch, tmp_path):
    """Admin + valid archive → 202, and the archive name lands in the flag file."""
    flag = tmp_path / ".restore-request"
    # Bypass on-disk archive lookup; pretend the archive exists.
    monkeypatch.setattr(
        "app.routers.backup._resolve_archive",
        lambda name: Path(f"/tmp/{name}"),
    )
    # Redirect the flag file into the test's tmp dir so we don't touch the repo.
    monkeypatch.setattr("app.core.jobs.restore_request_path", lambda: flag)
    monkeypatch.setattr("app.core.jobs.is_restore_in_progress", lambda: False)

    resp = await auth_client.post(RESTORE_PATH)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "restore_started"
    assert body["archive"] == VALID_NAME
    assert flag.read_text() == VALID_NAME


@pytest.mark.asyncio
async def test_restore_conflict_when_already_in_progress(auth_client, monkeypatch, tmp_path):
    """A pending flag file yields 409 and does not overwrite it."""
    flag = tmp_path / ".restore-request"
    flag.write_text(VALID_NAME)
    monkeypatch.setattr(
        "app.routers.backup._resolve_archive",
        lambda name: Path(f"/tmp/{name}"),
    )
    monkeypatch.setattr("app.core.jobs.restore_request_path", lambda: flag)
    monkeypatch.setattr("app.core.jobs.is_restore_in_progress", lambda: True)

    resp = await auth_client.post(RESTORE_PATH)
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]
    # Unchanged — trigger_restore was never called.
    assert flag.read_text() == VALID_NAME


@pytest.mark.asyncio
async def test_restore_status(auth_client, monkeypatch, tmp_path):
    """/restore/status reports the flag + last result marker."""
    flag = tmp_path / ".restore-request"
    result = tmp_path / ".restore-result"
    monkeypatch.setattr("app.core.jobs.restore_request_path", lambda: flag)
    monkeypatch.setattr("app.core.jobs.restore_result_path", lambda: result)

    # Nothing in flight yet.
    resp = await auth_client.get("/api/v1/backup/restore/status")
    assert resp.status_code == 200
    assert resp.json() == {"in_progress": False, "last": None}

    # Simulate the privileged unit writing a result marker.
    result.write_text('{"status": "ok", "archive": "backup_20260101_000000.tar.gz"}')
    flag.write_text(VALID_NAME)  # in-flight
    resp = await auth_client.get("/api/v1/backup/restore/status")
    assert resp.json()["in_progress"] is True
    assert resp.json()["last"]["status"] == "ok"
