"""Scheduled background jobs for the health tracker."""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.base import FamilyMember, HealthRecord, RecordType
from app.services.reminder_service import ReminderService
from app.services.health_alert_service import HealthAlertService
from app.models.health_alert import AlertType, AlertSeverity

logger = logging.getLogger(__name__)
settings = get_settings()


async def process_reminders():
    """Process due reminders and create notifications."""
    async with SessionLocal() as db:
        try:
            service = ReminderService(db)
            notifications = await service.process_due_reminders()
            await db.commit()
            if notifications:
                logger.info("Processed %d due reminders", len(notifications))
        except Exception:
            await db.rollback()
            logger.exception("Failed to process reminders")


async def rotate_backups():
    """Delete backup files older than 30 days."""
    backup_dir = Path("data/backups")
    if not backup_dir.exists():
        return

    now = time.time()
    cutoff = now - 30 * 86400  # 30 days
    deleted = 0

    for entry in os.scandir(backup_dir):
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            try:
                os.remove(entry.path)
                deleted += 1
            except OSError:
                logger.warning("Failed to delete old backup: %s", entry.path)

    if deleted:
        logger.info("Rotated %d backup files older than 30 days", deleted)


async def check_ai_providers():
    """Ping each configured AI provider and log availability."""
    import asyncio

    async def _check(name: str, coro) -> tuple[str, bool]:
        try:
            return name, await coro
        except Exception as exc:
            logger.warning("%s health check failed: %s", name, exc)
            return name, False

    # Resolve credentials once (stored value wins; .env fallback). Each call is
    # cached, so this is cheap and reflects UI-managed keys immediately.
    from app.core.provider_keys import resolve_provider_value

    openai_key = await resolve_provider_value("openai")
    gemini_key = await resolve_provider_value("gemini")
    groq_key = await resolve_provider_value("groq")
    openrouter_key = await resolve_provider_value("openrouter")
    ollama_url = await resolve_provider_value("ollama")

    async with httpx.AsyncClient(timeout=10) as client:
        tasks: list[asyncio.Task] = []

        if openai_key:

            async def _openai():
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}"},
                )
                return resp.status_code == 200

            tasks.append(asyncio.create_task(_check("OpenAI", _openai())))

        if gemini_key:

            async def _gemini():
                resp = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/"
                    "models/gemini-2.5-flash:generateContent",
                    json={"contents": [{"parts": [{"text": "hi"}]}]},
                    headers={"x-goog-api-key": gemini_key},
                )
                return resp.status_code == 200

            tasks.append(asyncio.create_task(_check("Gemini", _gemini())))

        if groq_key:

            async def _groq():
                resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}"},
                )
                return resp.status_code == 200

            tasks.append(asyncio.create_task(_check("Groq", _groq())))

        if openrouter_key:

            async def _openrouter():
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                )
                return resp.status_code == 200

            tasks.append(asyncio.create_task(_check("OpenRouter", _openrouter())))

        # Ollama (local)
        if ollama_url:

            async def _ollama():
                resp = await client.get(f"{ollama_url}/api/tags")
                if resp.status_code != 200:
                    return False
                model_names = [m["name"] for m in resp.json().get("models", [])]
                return any(settings.OLLAMA_MODEL in m for m in model_names)

            tasks.append(asyncio.create_task(_check("Ollama", _ollama())))

        if not tasks:
            logger.info("No AI providers configured — skipping health check")
            return

        checks = await asyncio.gather(*tasks)

    available = sum(1 for _, ok in checks if ok)
    logger.info(
        "AI provider health: %d/%d available (%s)",
        available,
        len(checks),
        ", ".join(f"{name}={'OK' if ok else 'DOWN'}" for name, ok in checks),
    )


def _extract_numeric(value: str) -> float | None:
    """Extract first numeric value from a string like '8.9 %' or '142 mg/dL'."""
    match = re.search(r"[\d.]+", value)
    return float(match.group()) if match else None


def _parse_ref_range(ref: str) -> tuple[float | None, float | None]:
    """Parse reference range string into (low, high) bounds.

    Handles: '< 6.0 %', '> 40 mg/dL', '70-100 mg/dL', '3.5-5.0'
    """
    ref_lower = ref.lower().strip()

    # Pattern: < value
    if match := re.match(r"<\s*([\d.]+)", ref_lower):
        return None, float(match.group(1))

    # Pattern: > value
    if match := re.match(r">\s*([\d.]+)", ref_lower):
        return float(match.group(1)), None

    # Pattern: value - value
    if match := re.search(r"([\d.]+)\s*[-–]\s*([\d.]+)", ref_lower):
        return float(match.group(1)), float(match.group(2))

    return None, None


async def detect_anomalies():
    """Scan recent lab records for out-of-range values and create health alerts."""
    async with SessionLocal() as db:
        try:
            result = await db.execute(
                select(HealthRecord)
                .options(selectinload(HealthRecord.family_member))
                .where(
                    HealthRecord.record_type.in_([RecordType.LAB_REPORT, RecordType.BLOOD_GLUCOSE]),
                    HealthRecord.is_deleted.is_(False),
                )
                .order_by(HealthRecord.record_date.desc())
                .limit(100)
            )
            records = list(result.scalars().all())

            alert_svc = HealthAlertService(db)

            # Batch-fetch existing duplicates per member to avoid N+1 queries
            member_ids = {r.family_member_id for r in records if r.clinical_data}
            existing_alerts: dict = {}
            for mid in member_ids:
                existing_alerts[mid] = await alert_svc.batch_check_duplicates(mid)

            created_count = 0
            for record in records:
                if not record.clinical_data:
                    continue
                try:
                    parsed = json.loads(record.clinical_data)
                    if parsed.get("_type") != "structured":
                        continue
                    tests = parsed.get("lab_results") or parsed.get("tests") or []
                    for test in tests:
                        test_name = test.get("test_name", "Unknown")
                        result_val = test.get("result", "")
                        ref_val = test.get("ref_value", "")
                        if not result_val or not ref_val:
                            continue

                        numeric = _extract_numeric(str(result_val))
                        low, high = _parse_ref_range(str(ref_val))
                        if numeric is None:
                            continue

                        out_of_range = False
                        direction = ""
                        if low is not None and numeric < low:
                            out_of_range = True
                            direction = "LOW"
                        elif high is not None and numeric > high:
                            out_of_range = True
                            direction = "HIGH"

                        if out_of_range:
                            logger.warning(
                                "Anomaly detected: %s = %s (ref: %s) — %s [record %s, date %s]",
                                test_name,
                                result_val,
                                ref_val,
                                direction,
                                record.id,
                                record.record_date,
                            )
                            # Check in-memory instead of per-test DB query
                            existing = existing_alerts.get(record.family_member_id, set())
                            if (test_name, record.record_date) in existing:
                                continue
                            # Also track newly created alerts to avoid duplicates within this run
                            existing.add((test_name, record.record_date))

                            created_count += 1
                            severity = (
                                AlertSeverity.CRITICAL
                                if direction == "HIGH"
                                else AlertSeverity.WARNING
                            )
                            await alert_svc.create_alert(
                                household_id=record.family_member.household_id,
                                member_id=record.family_member_id,
                                alert_type=AlertType.LAB_WARNING,
                                severity=severity,
                                title=f"{test_name} is {direction}: {result_val}",
                                message=(
                                    f"{test_name} value {result_val} is {direction} "
                                    f"the reference range ({ref_val}). "
                                    f"Recorded on {record.record_date}."
                                ),
                                record_id=record.id,
                                test_name=test_name,
                                value=str(result_val),
                                reference=ref_val,
                            )
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

            if created_count:
                await db.commit()
                logger.info("Anomaly scan complete: %d new alerts created", created_count)
            else:
                logger.info("Anomaly scan complete: no anomalies found")

        except Exception:
            await db.rollback()
            logger.exception("Failed to run anomaly detection")


async def detect_lab_anomalies_for_record(db, record) -> int:
    """Run the out-of-range lab check for a single record; create HealthAlerts.

    Reuses the same parsing/threshold logic as the batch :func:`detect_anomalies`
    job so a freshly-uploaded critical lab is flagged immediately instead of
    waiting up to 6h for the sweep. Safe to call on any record — no-ops (returns
    0) when the record isn't a lab/glucose record, has no structured data, or has
    no out-of-range values. Alerts are added to *db*'s session and committed by
    the caller's transaction. Never raises — anomaly detection must never block
    or fail a record save.
    """
    if record.record_type not in (RecordType.LAB_REPORT, RecordType.BLOOD_GLUCOSE):
        return 0
    if not record.clinical_data:
        return 0
    try:
        parsed = json.loads(record.clinical_data)
        if parsed.get("_type") != "structured":
            return 0
        tests = parsed.get("lab_results") or parsed.get("tests") or []
        if not tests:
            return 0

        # Resolve household_id via a one-column lookup — avoid touching the
        # family_member relationship, which may not be loaded in the caller's
        # session (lazy access raises MissingGreenlet under async SQLAlchemy).
        household_id = (
            await db.execute(
                select(FamilyMember.household_id).where(
                    FamilyMember.id == record.family_member_id
                )
            )
        ).scalar_one_or_none()
        if household_id is None:
            return 0

        alert_svc = HealthAlertService(db)
        existing = await alert_svc.batch_check_duplicates(record.family_member_id)
        created = 0
        for test in tests:
            test_name = test.get("test_name", "Unknown")
            result_val = test.get("result", "")
            ref_val = test.get("ref_value", "")
            if not result_val or not ref_val:
                continue
            numeric = _extract_numeric(str(result_val))
            if numeric is None:
                continue
            low, high = _parse_ref_range(str(ref_val))
            direction = ""
            if low is not None and numeric < low:
                direction = "LOW"
            elif high is not None and numeric > high:
                direction = "HIGH"
            if not direction:
                continue
            if (test_name, record.record_date) in existing:
                continue
            existing.add((test_name, record.record_date))
            severity = (
                AlertSeverity.CRITICAL if direction == "HIGH" else AlertSeverity.WARNING
            )
            await alert_svc.create_alert(
                household_id=household_id,
                member_id=record.family_member_id,
                alert_type=AlertType.LAB_WARNING,
                severity=severity,
                title=f"{test_name} is {direction}: {result_val}",
                message=(
                    f"{test_name} value {result_val} is {direction} the reference "
                    f"range ({ref_val}). Recorded on {record.record_date}."
                ),
                record_id=record.id,
                test_name=test_name,
                value=str(result_val),
                reference=ref_val,
            )
            created += 1
        if created:
            logger.info(
                "Real-time lab flag: %d alert(s) for record %s", created, record.id
            )
        return created
    except Exception:
        logger.exception("Real-time lab anomaly check failed for record %s", record.id)
        return 0


async def cleanup_staging_files():
    """Delete staging files older than 24 hours."""
    import time

    staging_dir = Path(settings.STORAGE_PATH) / "staging"
    if not staging_dir.exists():
        return

    now = time.time()
    cutoff = now - 86400  # 24 hours
    deleted = 0

    for entry in staging_dir.iterdir():
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            try:
                entry.unlink()
                deleted += 1
            except OSError:
                logger.warning("Failed to delete old staging file: %s", entry)

    if deleted:
        logger.info("Cleaned up %d staging files older than 24 hours", deleted)


async def verify_file_integrity():
    """Periodically verify SHA-256 hashes of stored attachments."""
    import hashlib

    async with SessionLocal() as db:
        try:
            # Check attachments with content_hash set
            from app.models.base import Attachment

            att_result = await db.execute(
                select(Attachment).where(Attachment.content_hash.isnot(None))
            )
            attachments = list(att_result.scalars().all())

            verified = 0
            failed = 0

            for att in attachments:
                file_path = Path(att.file_path)
                if not file_path.exists():
                    logger.warning("Integrity check: file missing for attachment %s", att.id)
                    failed += 1
                    continue

                try:
                    from app.core.storage import stream_plaintext

                    hasher = hashlib.sha256()
                    # Hash the PLAINTEXT (decrypt first when encrypted) so it
                    # matches the content_hash recorded at upload/migration.
                    async for chunk in stream_plaintext(file_path, att.encrypted):
                        hasher.update(chunk)

                    actual_hash = hasher.hexdigest()
                    if actual_hash != att.content_hash:
                        expected_prefix = (att.content_hash or "")[:12]
                        logger.error(
                            "Integrity check FAILED for attachment %s: expected %s, got %s",
                            att.id,
                            expected_prefix,
                            actual_hash[:12],
                        )
                        failed += 1
                    else:
                        verified += 1
                except Exception:
                    failed += 1
                    logger.exception("Integrity check error for attachment %s", att.id)

            if failed:
                logger.warning("File integrity check: %d verified, %d FAILED", verified, failed)
            else:
                logger.info("File integrity check: %d files verified OK", verified)

        except Exception:
            logger.exception("Failed to run file integrity verification")


async def backup_database():
    """Scheduled backup — gated by the primary household's configured schedule.

    The job ticks hourly (registered in main.py); it self-gates using the
    household's ``backup_schedule`` (off/daily/weekly) and the last-run
    timestamp in ``data/backups/.backup_state.json`` so the cadence can be
    changed live without rescheduling APScheduler.
    """
    schedule, _ = await get_backup_config()
    if schedule == "off":
        return
    interval = {"daily": 86400, "weekly": 604800}.get(schedule)
    if not interval:
        return
    state = read_backup_state()
    last_run = state.get("last_run")
    if last_run:
        try:
            elapsed = (
                datetime.now(timezone.utc) - datetime.fromisoformat(last_run)
            ).total_seconds()
        except ValueError:
            elapsed = interval  # corrupt timestamp → treat as due
        if elapsed < interval:
            return
    await run_backup_now()


async def run_backup_now() -> dict | None:
    """Create one compressed backup archive now, record state, apply retention.

    Returns ``{filename, size_bytes, created_at}`` or ``None`` on failure.
    Used by the scheduled job (after gating) and the manual ``POST /backup/run``.
    """
    archive = await asyncio.to_thread(create_backup_archive)
    if archive is None:
        return None
    created = datetime.now(timezone.utc).isoformat()
    state = read_backup_state()
    write_backup_state({**state, "last_run": created, "last_archive": archive.name})
    _, keep_max = await get_backup_config()
    apply_retention(keep_max)
    try:
        size = archive.stat().st_size
    except OSError:
        size = 0
    logger.info("Backup archive created: %s (%d bytes)", archive.name, size)
    return {"filename": archive.name, "size_bytes": size, "created_at": created}


# ── backup helpers (sync — run in a worker thread) ───────────────────────────


def _resolve_data_dir() -> Path:
    """On-disk data root: the directory holding the SQLite DB, falling back to
    the attachment-store's parent for PostgreSQL.

    Anchored to the DB location (not the process CWD) so the backup archives and
    the restore request/result markers land alongside the live ``health.db`` —
    i.e. the exact ``DATA_DIR`` the privileged ``restore-archive.sh`` swaps and
    the ``health-manager-restore.path`` unit watches (``/var/lib/health-manager/
    data`` in production). A CWD-relative ``data/backups`` would instead resolve
    under ``/opt/health-manager/backend/data/`` under systemd, which is read-only
    (``ProtectSystem=strict``) and is *not* where the restore unit looks — so
    backups would fail to write and restores would never trigger.
    """
    db_url = settings.DATABASE_URL
    if "sqlite" in db_url and "///" in db_url:
        # Mirrors _snapshot_sqlite's parsing: the path follows the first '///'.
        db_path = db_url.split("///", 1)[-1]
        if db_path:  # non-empty file path (not in-memory sqlite://)
            return Path(db_path).resolve().parent
    # PostgreSQL (no DB file) or in-memory sqlite: anchor to the attachment store.
    return Path(settings.STORAGE_PATH).resolve().parent


BACKUP_DIR = _resolve_data_dir() / "backups"

# Restore pipeline: the app (running as the unprivileged ``health-manager`` user)
# cannot restart its own systemd service, so a restore is delegated to the root
# ``health-manager-restore.service`` unit. That unit is triggered by a systemd
# path-unit watching RESTORE_REQUEST_NAME. The endpoint just drops the validated
# archive name into the flag file and returns 202; the privileged unit does the
# stop → swap → start and writes RESTORE_RESULT_NAME on completion.
RESTORE_REQUEST_NAME = ".restore-request"
RESTORE_RESULT_NAME = ".restore-result"


def restore_request_path() -> Path:
    """Flag file watched by ``health-manager-restore.path`` to trigger a restore.

    Lives alongside the backups under the persistent data dir
    (``/var/lib/health-manager/data/``), which the ``health-manager`` user owns
    and can therefore write.
    """
    return (BACKUP_DIR.parent / RESTORE_REQUEST_NAME).resolve()


def restore_result_path() -> Path:
    """JSON marker written by the privileged restore unit on completion."""
    return (BACKUP_DIR.parent / RESTORE_RESULT_NAME).resolve()


def is_restore_in_progress() -> bool:
    """True if a restore flag file is present (a restore is queued/running)."""
    return restore_request_path().exists()


def read_restore_result() -> dict | None:
    """Last restore outcome written by the privileged unit, or None."""
    try:
        return json.loads(restore_result_path().read_text())
    except (OSError, ValueError):
        return None


def trigger_restore(archive_name: str) -> None:
    """Atomically drop *archive_name* into the restore flag file.

    The temp-file + rename guarantees the watching path-unit fires exactly once
    on a complete value (no partial reads).
    """
    path = restore_request_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(archive_name)
    tmp.replace(path)


def create_backup_archive() -> Path | None:
    """Build a single ``backup_{ts}.tar.gz`` containing the DB + all attachments.

    SQLite is snapshotted via the online-backup API (``health.db``); PostgreSQL
    via ``pg_dump`` (``health.sql``). The encrypted-attachment store is added as
    ``attachments/``. gzip compresses the (text) DB dump; attachments are already
    encrypted so stay faithful but incompressible.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive = BACKUP_DIR / f"backup_{timestamp}.tar.gz"
    db_url = settings.DATABASE_URL
    # Write to a sibling .tmp and atomically rename on success so a crash,
    # SIGTERM, or ENOSPC mid-archive never leaves a truncated backup_*.tar.gz
    # that apply_retention would keep (by mtime) and an operator might restore
    # from. Mirrors the temp+replace used by _write_restore_request.
    tmp_archive = archive.with_name(archive.name + ".tmp")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            if db_url.startswith("sqlite"):
                db_name = "health.db"
                _snapshot_sqlite(db_url, tmp / db_name)
            else:
                db_name = "health.sql"
                _dump_postgres(db_url, tmp / db_name)
            # Bundle the at-rest ENCRYPTION_KEY so an offsite restore onto fresh
            # hardware can decrypt attachments/2FA secrets (the DB dump alone
            # leaves them unrecoverable — see AUDIT.md). The tar already carries
            # the plaintext DB, so a plaintext key bundle adds no new exposure.
            from app.core.backup_crypto import bundle_app_key_plaintext

            secrets_bundle = bundle_app_key_plaintext(
                getattr(settings, "ENCRYPTION_KEY", "") or None
            )
            if secrets_bundle:
                (tmp / "secrets.bundle").write_text(secrets_bundle)
            with tarfile.open(tmp_archive, "w:gz") as tar:
                tar.add(tmp / db_name, arcname=db_name)
                if secrets_bundle:
                    tar.add(tmp / "secrets.bundle", arcname="secrets.bundle")
                attachments_dir = Path(settings.STORAGE_PATH)
                if attachments_dir.exists():
                    tar.add(attachments_dir, arcname="attachments")
        tmp_archive.replace(archive)
        return archive
    except Exception:
        logger.exception("Backup archive creation failed")
        try:
            if tmp_archive.exists():
                tmp_archive.unlink()
        except OSError:
            pass
        return None


def _snapshot_sqlite(db_url: str, dest: Path) -> None:
    """Online-backup the SQLite DB to *dest* (atomic, safe while in use)."""
    import sqlite3

    db_path = db_url.split("///", 1)[-1]
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _dump_postgres(db_url: str, dest: Path) -> None:
    """Dump PostgreSQL via pg_dump to *dest* (plain SQL; gzip happens in the tar)."""
    pg_url = db_url.replace("+asyncpg", "")
    result = subprocess.run(["pg_dump", pg_url], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr[:200]}")
    dest.write_text(result.stdout)


def _backup_state_path() -> Path:
    return BACKUP_DIR / ".backup_state.json"


def read_backup_state() -> dict:
    try:
        return json.loads(_backup_state_path().read_text())
    except Exception:
        return {}


def write_backup_state(state: dict) -> None:
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        _backup_state_path().write_text(json.dumps(state))
    except Exception:
        logger.warning("Could not write backup state file")


def list_backup_archives() -> list[dict]:
    """List ``backup_*.tar.gz`` newest-first as ``{name, size_bytes, created_at}``."""
    if not BACKUP_DIR.exists():
        return []
    archives = sorted(
        BACKUP_DIR.glob("backup_*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out = []
    for p in archives:
        try:
            st = p.stat()
        except OSError:
            continue
        out.append(
            {
                "name": p.name,
                "size_bytes": st.st_size,
                "created_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return out


def apply_retention(keep_max: int) -> None:
    """Delete oldest backups beyond *keep_max* (count-based)."""
    if not BACKUP_DIR.exists() or keep_max < 1:
        return
    archives = sorted(
        BACKUP_DIR.glob("backup_*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in archives[keep_max:]:
        try:
            old.unlink()
        except OSError:
            logger.warning("Could not delete old backup: %s", old)


def get_backup_status() -> dict:
    """Storage overview for the Data tab."""

    def _dir_size(path: Path) -> int:
        if not path.exists():
            return 0
        total = 0
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except OSError:
                    pass
        return total

    db_size = 0
    if settings.DATABASE_URL.startswith("sqlite"):
        db_path = Path(settings.DATABASE_URL.split("///", 1)[-1])
        if db_path.exists():
            db_size = db_path.stat().st_size

    du = shutil.disk_usage(".")
    state = read_backup_state()
    return {
        "attachments_bytes": _dir_size(Path(settings.STORAGE_PATH)),
        "database_bytes": db_size,
        "backups_bytes": _dir_size(BACKUP_DIR),
        "disk": {"total": du.total, "used": du.used, "free": du.free},
        "last_run": state.get("last_run"),
        "last_archive": state.get("last_archive"),
    }


async def get_backup_config() -> tuple[str, int]:
    """Read the primary household's backup schedule + retention (``off``, 10 default).

    Single-household family-server assumption: the oldest household's settings
    drive the server-wide backup schedule.
    """
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models.base import Household

    try:
        async with SessionLocal() as db:
            result = await db.execute(select(Household).order_by(Household.created_at).limit(1))
            hh = result.scalar_one_or_none()
            if hh and hh.settings_json:
                data = json.loads(hh.settings_json)
                schedule = data.get("backup_schedule", "off")
                keep_max = int(data.get("backup_keep_max", 10))
                return (
                    schedule if schedule in ("off", "daily", "weekly") else "off",
                    max(1, keep_max),
                )
    except Exception:
        logger.exception("Could not read backup config; defaulting to off")
    return ("off", 10)


async def migrate_attachments_to_encrypted() -> dict:
    """One-time migration: optimize + encrypt existing plaintext attachments.

    Closes the storage-at-rest gap for files written before encryption was
    enabled. Idempotent (skips ``encrypted=True``). Per-file safe:
    write the new encrypted file → round-trip verify → update the row → delete
    the old raw file. Graceful without ghostscript (encrypts without optimizing).

    NOTE: PDF optimization is lossy (ghostscript downsamples embedded images);
    recommend a backup before running. Returns ``{migrated, failed}``.
    """
    import hashlib
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models.base import Attachment
    from app.core.storage import _store_plaintext_file, _safe_unlink
    from app.core.encryption import decrypt_file

    migrated = 0
    failed = 0
    skipped = 0  # un-encrypted rows whose file is already gone (not a failure)
    async with SessionLocal() as db:
        result = await db.execute(select(Attachment).where(Attachment.encrypted.is_(False)))
        attachments = list(result.scalars().all())
        if not attachments:
            return {"migrated": 0, "skipped": 0, "failed": 0}

        for att in attachments:
            old_path = Path(att.file_path)
            if not old_path.exists():
                # A missing file isn't a migration failure — the row's file is
                # already gone (it 404s on download regardless). Skip quietly
                # (DEBUG) and don't count it as failed, so a handful of stale
                # orphans don't log a scary "N failed" every boot. Remove the
                # orphaned rows with the one-off cleanup script if desired.
                logger.debug("attachment migration: file missing for %s — skipping", att.id)
                skipped += 1
                continue
            try:
                ext = old_path.suffix or ".bin"
                new_path, new_hash = await _store_plaintext_file(old_path, ext, att.mime_type)
                # Round-trip verify before committing the row.
                plain = await decrypt_file(new_path)
                if hashlib.sha256(plain).hexdigest() != new_hash:
                    logger.error("attachment migration: verify failed for %s", att.id)
                    failed += 1
                    continue
                att.content_hash = new_hash
                att.file_path = str(new_path)
                att.file_size = len(plain)  # plaintext size
                att.encrypted = True
                await db.commit()
                # Only now safe to remove the old raw file.
                if old_path.resolve() != new_path.resolve():
                    _safe_unlink(old_path)
                migrated += 1
            except Exception:
                await db.rollback()
                logger.exception("attachment migration: failed for %s", att.id)
                failed += 1

    logger.info(
        "attachment migration complete: %d migrated, %d skipped, %d failed",
        migrated,
        skipped,
        failed,
    )
    return {"migrated": migrated, "skipped": skipped, "failed": failed}
