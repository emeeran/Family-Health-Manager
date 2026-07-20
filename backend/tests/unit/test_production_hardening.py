"""Unit tests for the production-hardening changes.

Covers the new pure-logic code paths that are most regression-prone:
- encryption dual-key decrypt + secret helpers (encryption.py)
- password length cap (security.py)
- SQLite + attachments backup (jobs.py)
- scheduler single-instance lock helpers (scheduler.py)
"""

import os
import sqlite3
import tarfile
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

import app.core.encryption as enc
import app.core.jobs as jobs
import app.core.scheduler as scheduler
from app.core.security import validate_password_strength


def _settings(enc_key: str = "", secret: str = "test-secret-key-for-unit-tests") -> SimpleNamespace:
    return SimpleNamespace(ENCRYPTION_KEY=enc_key, SECRET_KEY=secret)


# ── encryption ──────────────────────────────────────────────────────────────


def test_secret_round_trip(monkeypatch):
    monkeypatch.setattr(enc, "get_settings", lambda: _settings(Fernet.generate_key().decode()))
    enc.clear_encryption_cache()
    ct = enc.encrypt_secret("JBSWY3DPEHPK3PXP")
    assert ct != "JBSWY3DPEHPK3PXP"  # actually encrypted
    assert enc.decrypt_secret(ct) == "JBSWY3DPEHPK3PXP"
    assert enc.is_secret_encrypted(ct) is True


def test_secret_legacy_plaintext_read_through(monkeypatch):
    """Plaintext secrets (older installs) are returned unchanged on read."""
    monkeypatch.setattr(enc, "get_settings", lambda: _settings())  # legacy-derived key
    enc.clear_encryption_cache()
    assert enc.decrypt_secret("JBSWY3DPEHPK3PXP") == "JBSWY3DPEHPK3PXP"
    assert enc.is_secret_encrypted("JBSWY3DPEHPK3PXP") is False
    assert enc.is_secret_encrypted(None) is False


def test_dual_key_decrypt_legacy_payload(monkeypatch):
    """Files/secrets encrypted with the legacy key stay readable after a
    dedicated ENCRYPTION_KEY is introduced (dual-key fallback)."""
    # Encrypt with the legacy-derived key.
    monkeypatch.setattr(enc, "get_settings", lambda: _settings())
    enc.clear_encryption_cache()
    legacy_ct = enc.encrypt_secret("payload")

    # Switch to a fresh dedicated key.
    monkeypatch.setattr(enc, "get_settings", lambda: _settings(Fernet.generate_key().decode()))
    enc.clear_encryption_cache()
    assert enc.decrypt_secret(legacy_ct) == "payload"  # readable via fallback


def test_bytes_dual_key_decrypt_legacy(monkeypatch):
    monkeypatch.setattr(enc, "get_settings", lambda: _settings())
    enc.clear_encryption_cache()
    blob = enc.encrypt_bytes(b"file-contents")

    monkeypatch.setattr(enc, "get_settings", lambda: _settings(Fernet.generate_key().decode()))
    enc.clear_encryption_cache()
    assert enc.decrypt_bytes(blob) == b"file-contents"


# ── password strength cap ───────────────────────────────────────────────────


def test_password_rejects_pathologically_long():
    # > 4096 chars must be rejected (argon2 DoS guard).
    assert validate_password_strength("Aa1!" * 2000) is False


def test_password_accepts_strong_short():
    assert validate_password_strength("Abcdef1!") is True


def test_password_rejects_short():
    assert validate_password_strength("Aa1!") is False


# ── scheduler lock ──────────────────────────────────────────────────────────


def test_scheduler_lock_acquire_and_release(tmp_path, monkeypatch):
    # Isolate the lock to a temp path so a concurrently-running dev server
    # (which may hold data/scheduler.lock) doesn't make the test fail.
    monkeypatch.setattr(scheduler, "_SCHEDULER_LOCK_PATH", tmp_path / "scheduler.lock")
    scheduler._release_scheduler_lock()
    assert scheduler._try_acquire_scheduler_lock() is True
    scheduler._release_scheduler_lock()  # must not raise


@pytest.mark.asyncio
async def test_start_scheduler_no_jobs_returns_early(monkeypatch):
    """With no jobs registered the scheduler exits without acquiring the lock."""
    called = {"lock": False}

    def _fail_if_called():
        called["lock"] = True
        return True

    monkeypatch.setattr(scheduler, "_jobs", {})
    monkeypatch.setattr(scheduler, "_try_acquire_scheduler_lock", _fail_if_called)
    await scheduler.start_scheduler()
    assert called["lock"] is False  # early-returned before touching the lock


# ── reset-database requires admin (signature guard) ─────────────────────────


def test_reset_database_route_requires_admin():
    """The reset-database endpoint must depend on require_admin (not just auth)."""
    import inspect
    from app.routers import household

    route = next(
        r for r in household.router.routes if getattr(r, "path", "").endswith("/reset-database")
    )
    sig = inspect.signature(route.endpoint)
    # The dependency callables in the signature:
    deps = [d.default for d in sig.parameters.values() if hasattr(d.default, "dependency")]
    dep_fns = [getattr(d.dependency, "__name__", "") for d in deps]
    assert "require_admin" in dep_fns, f"reset-database must depend on require_admin; got {dep_fns}"


# ── on-server compressed backups (Data tab) ─────────────────────────────────


def _seed_db(path) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (1), (2)")
    con.commit()
    con.close()


def test_backup_dir_anchored_to_database_dir_not_cwd(monkeypatch, tmp_path):
    """BACKUP_DIR must resolve to the live DB's directory (the restore script's
    ``DATA_DIR``), not a CWD-relative ``data/backups``. The latter lands under
    ``/opt/health-manager/backend/data`` in production — read-only under systemd
    hardening, and not where ``restore-archive.sh`` or the path-unit looks, so
    backups fail to write and restores never trigger."""
    db_dir = tmp_path / "var" / "lib" / "health-manager" / "data"
    db_dir.mkdir(parents=True)
    db_file = db_dir / "health.db"
    db_file.write_bytes(b"")
    monkeypatch.setattr(
        jobs,
        "settings",
        SimpleNamespace(
            DATABASE_URL=f"sqlite+aiosqlite:///{db_file}",
            STORAGE_PATH=str(tmp_path / "attachments"),
        ),
    )
    assert jobs._resolve_data_dir() == db_file.resolve().parent
    assert (jobs._resolve_data_dir() / "backups") == db_file.resolve().parent / "backups"


def test_backup_dir_falls_back_to_storage_for_postgres(monkeypatch, tmp_path):
    """With no DB file path (PostgreSQL), anchor to the attachment store's dir."""
    storage = tmp_path / "var" / "lib" / "health-manager" / "data" / "attachments"
    storage.mkdir(parents=True)
    monkeypatch.setattr(
        jobs,
        "settings",
        SimpleNamespace(
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/hm",
            STORAGE_PATH=str(storage),
        ),
    )
    assert jobs._resolve_data_dir() == storage.resolve().parent


def test_create_backup_archive_contains_db_and_originals(tmp_path, monkeypatch):
    src_db = tmp_path / "health.db"
    _seed_db(src_db)
    storage = tmp_path / "storage"
    (storage / "files").mkdir(parents=True)
    (storage / "files" / "record.pdf").write_bytes(b"%PDF-encrypted-bytes")
    backups = tmp_path / "backups"
    monkeypatch.setattr(
        jobs,
        "settings",
        SimpleNamespace(DATABASE_URL=f"sqlite:///{src_db}", STORAGE_PATH=str(storage)),
    )
    monkeypatch.setattr(jobs, "BACKUP_DIR", backups)

    archive = jobs.create_backup_archive()
    assert archive is not None
    assert archive.name.startswith("backup_") and archive.name.endswith(".tar.gz")

    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "health.db" in names
    assert any(n.startswith("attachments/files/record.pdf") for n in names)


def test_create_backup_archive_is_atomic_on_failure(tmp_path, monkeypatch):
    """A crash / ENOSPC / SIGTERM mid-archive must not leave a truncated
    backup_*.tar.gz behind — retention keeps archives by mtime, so a partial
    file could otherwise be restored from. The write goes to a .tmp sibling and
    only renames on success."""
    from pathlib import Path

    src_db = tmp_path / "health.db"
    _seed_db(src_db)
    storage = tmp_path / "storage"
    (storage / "files").mkdir(parents=True)
    backups = tmp_path / "backups"
    monkeypatch.setattr(
        jobs,
        "settings",
        SimpleNamespace(DATABASE_URL=f"sqlite:///{src_db}", STORAGE_PATH=str(storage)),
    )
    monkeypatch.setattr(jobs, "BACKUP_DIR", backups)

    def _boom(*args, **kwargs):
        # Simulate a partially-written archive then a failure mid-tar.
        Path(args[0]).write_bytes(b"PARTIAL")
        raise OSError("simulated mid-archive failure")

    monkeypatch.setattr(jobs.tarfile, "open", _boom)

    assert jobs.create_backup_archive() is None
    # No final archive and no leftover .tmp sibling in the backup dir.
    assert not list(backups.glob("backup_*.tar.gz"))
    assert not list(backups.glob("*.tmp"))


def test_list_backup_archives_filters_and_sorts(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "BACKUP_DIR", tmp_path)
    (tmp_path / "backup_20260101_000000.tar.gz").write_bytes(b"a")
    (tmp_path / "backup_20260102_000000.tar.gz").write_bytes(b"bb")
    (tmp_path / "notabackup.txt").write_bytes(b"x")  # ignored
    (tmp_path / ".backup_state.json").write_text("{}")  # ignored

    archs = jobs.list_backup_archives()
    assert len(archs) == 2
    assert all(a["name"].startswith("backup_") for a in archs)
    assert all("size_bytes" in a and "created_at" in a for a in archs)


def test_apply_retention_keeps_newest_n(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "BACKUP_DIR", tmp_path)
    base = 1_700_000_000
    for i in range(5):
        f = tmp_path / f"backup_2026010{i}_000000.tar.gz"
        f.write_bytes(b"x")
        os.utime(f, (base + i, base + i))  # increasing mtime

    jobs.apply_retention(3)

    remaining = sorted(p.name for p in tmp_path.glob("backup_*.tar.gz"))
    # newest 3 by mtime → i = 2, 3, 4
    assert remaining == [
        "backup_20260102_000000.tar.gz",
        "backup_20260103_000000.tar.gz",
        "backup_20260104_000000.tar.gz",
    ]


def test_backup_state_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "BACKUP_DIR", tmp_path)
    assert jobs.read_backup_state() == {}
    jobs.write_backup_state({"last_run": "2026-06-17T00:00:00+00:00", "last_archive": "x.tar.gz"})
    state = jobs.read_backup_state()
    assert state["last_run"] == "2026-06-17T00:00:00+00:00"
    assert state["last_archive"] == "x.tar.gz"


@pytest.mark.asyncio
async def test_backup_database_skips_when_off(monkeypatch):
    """Schedule 'off' → run_backup_now must not be called."""

    async def _off_cfg():
        return ("off", 10)

    async def _fail():
        raise AssertionError("should not run when schedule is off")

    monkeypatch.setattr(jobs, "get_backup_config", _off_cfg)
    monkeypatch.setattr(jobs, "run_backup_now", _fail)
    await jobs.backup_database()  # returns without raising
