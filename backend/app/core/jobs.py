"""Scheduled background jobs for the health tracker."""
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.base import HealthRecord, RecordType
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

    async with httpx.AsyncClient(timeout=10) as client:
        tasks: list[asyncio.Task] = []

        if settings.OPENAI_API_KEY:
            async def _openai():
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                )
                return resp.status_code == 200
            tasks.append(asyncio.create_task(_check("OpenAI", _openai())))

        if settings.GEMINI_API_KEY:
            async def _gemini():
                resp = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/"
                    "models/gemini-2.5-flash:generateContent",
                    json={"contents": [{"parts": [{"text": "hi"}]}]},
                    headers={"x-goog-api-key": settings.GEMINI_API_KEY},
                )
                return resp.status_code == 200
            tasks.append(asyncio.create_task(_check("Gemini", _gemini())))

        if settings.GROQ_API_KEY:
            async def _groq():
                resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                )
                return resp.status_code == 200
            tasks.append(asyncio.create_task(_check("Groq", _groq())))

        if settings.OPENROUTER_API_KEY:
            async def _openrouter():
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                )
                return resp.status_code == 200
            tasks.append(asyncio.create_task(_check("OpenRouter", _openrouter())))

        # Ollama (local)
        if settings.OLLAMA_LOCAL_URL:
            async def _ollama():
                resp = await client.get(f"{settings.OLLAMA_LOCAL_URL}/api/tags")
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
                                test_name, result_val, ref_val, direction,
                                record.id, record.record_date,
                            )
                            # Check in-memory instead of per-test DB query
                            existing = existing_alerts.get(record.family_member_id, set())
                            if (test_name, record.record_date) in existing:
                                continue
                            # Also track newly created alerts to avoid duplicates within this run
                            existing.add((test_name, record.record_date))

                            created_count += 1
                            severity = AlertSeverity.CRITICAL if direction == "HIGH" else AlertSeverity.WARNING
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


async def backup_database():
    """Create a gzipped database backup using pg_dump.

    Only runs when DATABASE_URL is PostgreSQL. Skips silently otherwise.
    Saves backups to data/backups/ with timestamp filename.
    """
    db_url = settings.DATABASE_URL
    if not db_url.startswith("postgresql"):
        logger.debug("Backup skipped — not using PostgreSQL")
        return

    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"health_{timestamp}.sql.gz"

    try:
        # pg_dump doesn't accept asyncpg driver, convert to standard psycopg format
        pg_url = db_url.replace("+asyncpg", "")
        result = subprocess.run(
            ["pg_dump", pg_url],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error("pg_dump failed: %s", result.stderr)
            return

        import gzip
        with gzip.open(backup_file, "wt") as f:
            f.write(result.stdout)

        logger.info("Database backup created: %s (%d bytes)", backup_file.name, backup_file.stat().st_size)
    except FileNotFoundError:
        logger.warning("pg_dump not found — database backup skipped")
    except subprocess.TimeoutExpired:
        logger.error("pg_dump timed out after 300s")
    except Exception:
        logger.exception("Database backup failed")
