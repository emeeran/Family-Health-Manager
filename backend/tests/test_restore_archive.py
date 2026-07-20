"""End-to-end test for the disaster-recovery restore script.

``packaging/restore-archive.sh`` is the ONLY restore path for a packaged install,
so it must actually work. The script takes env overrides (``DATA_DIR`` /
``APP_SVC`` / ``APP_USER``) precisely so this test can run the real script against
a throwaway layout without root or systemd. We seed a "current" DB, build a valid
backup archive holding a different DB, trigger the restore, and assert the DB was
swapped, a pre-restore safety backup was taken, and the result marker says ok.

A recording fake `systemctl` is put on PATH and asserted never to be invoked —
the test must NEVER touch a real systemd unit (an earlier version silently did,
because `${APP_SVC:-default}` treats an empty value as unset).
"""

import json
import os
import pwd
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path

import pytest

RESTORE_SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "restore-archive.sh"


def _current_user() -> str:
    return pwd.getpwuid(os.getuid()).pw_name


def _make_db(path: Path, marker: str) -> None:
    """Create a SQLite DB whose `restore_marker` row identifies its origin."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE restore_marker (value TEXT)")
    conn.execute("INSERT INTO restore_marker VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def _read_marker(path: Path) -> str | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT value FROM restore_marker").fetchone()
    conn.close()
    return row[0] if row else None


def _build_archive(archive_path: Path, db_marker: str) -> None:
    """Build a valid backup_*.tar.gz containing a health.db snapshot at its root."""
    with tempfile.TemporaryDirectory() as staging:
        _make_db(Path(staging) / "health.db", db_marker)
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(Path(staging) / "health.db", arcname="health.db")


@pytest.fixture
def systemctl_guard(tmp_path):
    """Prepend a recording fake `systemctl` to PATH for the subprocess.

    Returns (env_path, log_path). The log must stay empty: the restore script
    under test must never invoke systemctl (APP_SVC="" skips it). A non-empty log
    means the script is touching a real systemd unit from the test — a regression.
    """
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    log = tmp_path / "systemctl.log"
    (fake_bin / "systemctl").write_text(f'#!/bin/bash\necho "systemctl $*" >> "{log}"\nexit 0\n')
    (fake_bin / "systemctl").chmod(0o755)
    env_path = f"{fake_bin}:{os.environ.get('PATH', '')}"
    return env_path, log


def _run_restore(data_dir: Path, env_path: str) -> subprocess.CompletedProcess:
    """Run the restore script against a temp DATA_DIR, skipping systemctl."""
    env = {
        **os.environ,
        "PATH": env_path,
        "DATA_DIR": str(data_dir),
        "APP_SVC": "",  # skip service control
        "CADDY_SVC": "",  # skip Caddy service control too
        "APP_USER": _current_user(),
    }
    return subprocess.run(
        ["bash", str(RESTORE_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def restore_layout(tmp_path):
    """A throwaway DATA_DIR: a 'current' DB + a valid restore archive queued."""
    data_dir = tmp_path / "data"
    (data_dir / "attachments").mkdir(parents=True)
    (data_dir / "attachments" / "current.txt").write_text("current attachment")
    backups = data_dir / "backups"
    backups.mkdir()
    _make_db(data_dir / "health.db", "CURRENT")

    archive_name = "backup_20260101_120000.tar.gz"
    _build_archive(backups / archive_name, "ARCHIVED")
    (data_dir / ".restore-request").write_text(archive_name)
    return data_dir, archive_name


def _assert_no_systemctl(log: Path) -> None:
    calls = log.read_text() if log.exists() else ""
    assert not calls, f"restore invoked systemctl under test (must be skipped):\n{calls}"


def test_restore_swaps_db_and_writes_ok_result(restore_layout, systemctl_guard):
    data_dir, archive_name = restore_layout
    env_path, systemctl_log = systemctl_guard
    result = _run_restore(data_dir, env_path)
    assert result.returncode == 0, (
        f"restore failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
    )
    _assert_no_systemctl(systemctl_log)

    # DB swapped to the archive's snapshot.
    assert _read_marker(data_dir / "health.db") == "ARCHIVED"
    # Result marker says ok, names the archive, and references a safety backup.
    result_json = json.loads((data_dir / ".restore-result").read_text())
    assert result_json["status"] == "ok"
    assert result_json["archive"] == archive_name
    pre = result_json["pre_restore_backup"]
    assert pre.startswith("backup_prerestore_")
    assert (data_dir / "backups" / pre).exists()
    # Flag file consumed.
    assert not (data_dir / ".restore-request").exists()


def test_restore_safety_backup_holds_pre_restore_state(restore_layout, systemctl_guard, tmp_path):
    """The undo path: the pre-restore safety backup must capture the CURRENT db,
    so a bad restore can be rolled back."""
    data_dir, _ = restore_layout
    env_path, systemctl_log = systemctl_guard
    result = _run_restore(data_dir, env_path)
    assert result.returncode == 0, result.stderr
    _assert_no_systemctl(systemctl_log)

    result_json = json.loads((data_dir / ".restore-result").read_text())
    pre_archive = data_dir / "backups" / result_json["pre_restore_backup"]
    with tarfile.open(pre_archive, "r:gz") as tar:
        with tar.extractfile(tar.getmember("health.db")) as f:
            tmp_db = tmp_path / "pre.db"
            tmp_db.write_bytes(f.read())
    assert _read_marker(tmp_db) == "CURRENT"  # safety backup = pre-restore state


def test_restore_rejects_invalid_archive_name(tmp_path, systemctl_guard):
    """A path-traversal / malformed name must be rejected, not executed."""
    data_dir = tmp_path / "data"
    (data_dir / "backups").mkdir(parents=True)
    _make_db(data_dir / "health.db", "CURRENT")
    (data_dir / ".restore-request").write_text("../../etc/passwd")

    env_path, systemctl_log = systemctl_guard
    result = _run_restore(data_dir, env_path)
    assert result.returncode == 1
    _assert_no_systemctl(systemctl_log)
    result_json = json.loads((data_dir / ".restore-result").read_text())
    assert result_json["status"] == "error"
    # Current DB untouched.
    assert _read_marker(data_dir / "health.db") == "CURRENT"


def test_restore_restarts_caddy_after_backend(tmp_path):
    """The restore must restart Caddy too. The Caddy unit has
    `Requires=health-manager.service`, so stopping the backend during a restore
    also stops Caddy — but starting the backend does NOT start Caddy back.
    Without an explicit `systemctl start health-manager-caddy.service` the site
    is left unreachable after a successful DB swap (can't log in)."""
    data_dir = tmp_path / "data"
    (data_dir / "attachments").mkdir(parents=True)
    _make_db(data_dir / "health.db", "CURRENT")
    backups = data_dir / "backups"
    backups.mkdir()
    archive_name = "backup_20260101_120000.tar.gz"
    _build_archive(backups / archive_name, "ARCHIVED")
    (data_dir / ".restore-request").write_text(archive_name)

    # Recording fake systemctl (APP_SVC + CADDY_SVC default to the real names).
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    log = tmp_path / "systemctl.log"
    (fake_bin / "systemctl").write_text(f'#!/bin/bash\necho "systemctl $*" >> "{log}"\nexit 0\n')
    (fake_bin / "systemctl").chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "DATA_DIR": str(data_dir),
        "APP_USER": _current_user(),
    }
    result = subprocess.run(["bash", str(RESTORE_SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"restore failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"

    calls = log.read_text() if log.exists() else ""
    assert "start health-manager-caddy.service" in calls, (
        f"restore did not start Caddy (site would be unreachable):\n{calls}"
    )
    assert "start health-manager.service" in calls  # backend too, of course
    # And it was stopped during the swap (the whole point).
    assert "stop health-manager-caddy.service" in calls


def test_restore_handles_large_archive(tmp_path, systemctl_guard):
    """A large archive (big incompressible attachments → slow ``tar -tzf``) must
    still restore. Under ``set -o pipefail`` the old ``tar -tzf | grep -qx``
    check failed spuriously on such archives — tar took SIGPIPE on stdout once
    grep was done, and pipefail turned that into a false "no health.db", breaking
    every restore of a real (multi-100MB) backup. The temp-file validation fixes
    it; this guards the regression (~30MB reliably reproduces the old failure)."""
    data_dir = tmp_path / "data"
    (data_dir / "attachments").mkdir(parents=True)
    _make_db(data_dir / "health.db", "CURRENT")
    backups = data_dir / "backups"
    backups.mkdir()
    archive_name = "backup_20260101_120000.tar.gz"

    with tempfile.TemporaryDirectory() as staging:
        _make_db(Path(staging) / "health.db", "ARCHIVED")
        att = Path(staging) / "attachments"
        att.mkdir()
        for i in range(6):
            (att / f"big_{i}.bin").write_bytes(os.urandom(5_000_000))  # ~30MB total
        with tarfile.open(backups / archive_name, "w:gz") as tar:
            tar.add(Path(staging) / "health.db", arcname="health.db")
            tar.add(att, arcname="attachments")
    (data_dir / ".restore-request").write_text(archive_name)

    env_path, systemctl_log = systemctl_guard
    result = _run_restore(data_dir, env_path)
    assert result.returncode == 0, f"restore failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
    _assert_no_systemctl(systemctl_log)
    assert _read_marker(data_dir / "health.db") == "ARCHIVED"
    result_json = json.loads((data_dir / ".restore-result").read_text())
    assert result_json["status"] == "ok"


def test_app_archive_then_script_restore_round_trip(tmp_path, monkeypatch, systemctl_guard):
    """End-to-end through the real code paths: the APP builds a backup archive
    and writes the restore flag (``create_backup_archive`` + ``trigger_restore``),
    then the SCRIPT restores from it.

    Ties the app side — ``_resolve_data_dir`` → ``BACKUP_DIR`` →
    ``restore_request_path`` — to the script's ``$DATA_DIR``. Before the
    ``BACKUP_DIR`` anchoring fix these pointed at different places, so the flag
    the app wrote was never the flag the script (or the systemd path-unit) read.
    """
    from types import SimpleNamespace

    import app.core.jobs as jobs

    data_dir = tmp_path / "data"
    (data_dir / "attachments").mkdir(parents=True)
    db_file = data_dir / "health.db"
    _make_db(db_file, "CURRENT")
    (data_dir / "attachments" / "f.txt").write_text("encrypted-bytes")

    # Point the app at this data dir the way prod config does (absolute DB path),
    # and recompute BACKUP_DIR from it so trigger_restore targets the right place.
    monkeypatch.setattr(
        jobs,
        "settings",
        SimpleNamespace(
            DATABASE_URL=f"sqlite+aiosqlite:///{db_file}",
            STORAGE_PATH=str(data_dir / "attachments"),
        ),
    )
    monkeypatch.setattr(jobs, "BACKUP_DIR", jobs._resolve_data_dir() / "backups")

    # 1. App builds a real archive snapshotting the CURRENT db.
    archive = jobs.create_backup_archive()
    assert archive is not None and archive.exists()
    archive_name = archive.name

    # 2. Simulate post-backup changes to the live db.
    conn = sqlite3.connect(db_file)
    conn.execute("DELETE FROM restore_marker")
    conn.execute("INSERT INTO restore_marker VALUES (?)", ("MODIFIED",))
    conn.commit()
    conn.close()
    assert _read_marker(db_file) == "MODIFIED"

    # 3. App writes the restore flag — and it lands exactly where the script reads.
    jobs.trigger_restore(archive_name)
    flag = data_dir / ".restore-request"
    assert flag.read_text() == archive_name

    # 4. Run the privileged restore script (no systemd).
    env_path, systemctl_log = systemctl_guard
    result = _run_restore(data_dir, env_path)
    assert result.returncode == 0, f"restore failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
    _assert_no_systemctl(systemctl_log)

    # 5. DB reverted to the archived snapshot; result ok; safety backup present.
    assert _read_marker(db_file) == "CURRENT"
    result_json = json.loads((data_dir / ".restore-result").read_text())
    assert result_json["status"] == "ok"
    assert (data_dir / "backups" / result_json["pre_restore_backup"]).exists()
    # Flag consumed.
    assert not (data_dir / ".restore-request").exists()
