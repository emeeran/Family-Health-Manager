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
    (fake_bin / "systemctl").write_text(
        f'#!/bin/bash\necho "systemctl $*" >> "{log}"\nexit 0\n'
    )
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
    assert result.returncode == 0, f"restore failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
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
