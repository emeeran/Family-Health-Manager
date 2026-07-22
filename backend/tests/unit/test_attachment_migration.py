"""Tests for the attachment at-rest-encryption startup migration.

Covers the key behaviour: an un-encrypted attachment whose file is already gone
counts as ``skipped`` (logged at DEBUG), NOT as ``failed`` — so stale orphans
don't surface a scary "N failed" on every boot. Uses a fake session; no files,
no real DB rows.
"""

from contextlib import asynccontextmanager

from app.core import database, jobs


class _FakeAtt:
    def __init__(self, att_id: str, file_path: str):
        self.id = att_id
        self.file_path = file_path
        self.mime_type = "application/octet-stream"


def _patch_session(monkeypatch, attachments):
    class _Result:
        def scalars(self):
            class _S:
                def all(self):
                    return list(attachments)

            return _S()

    class _FakeDB:
        async def execute(self, _stmt):
            return _Result()

        async def commit(self):
            pass

        async def rollback(self):
            pass

    @asynccontextmanager
    async def _fake_sessionlocal():
        yield _FakeDB()

    # migrate_attachments_to_encrypted imports SessionLocal from app.core.database
    # at call time, so patch the module attribute it reads.
    monkeypatch.setattr(database, "SessionLocal", _fake_sessionlocal)


async def test_missing_file_is_skipped_not_failed(monkeypatch, tmp_path):
    """A row whose file is gone is skipped (DEBUG), not counted as failed."""
    missing = _FakeAtt("orph-1", str(tmp_path / "gone.bin"))
    _patch_session(monkeypatch, [missing])
    result = await jobs.migrate_attachments_to_encrypted()
    assert result == {"migrated": 0, "skipped": 1, "failed": 0}


async def test_no_attachments_returns_zeroes(monkeypatch):
    _patch_session(monkeypatch, [])
    result = await jobs.migrate_attachments_to_encrypted()
    assert result == {"migrated": 0, "skipped": 0, "failed": 0}
