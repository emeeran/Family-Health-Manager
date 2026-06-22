"""Backup and restore router."""

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jobs
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, get_household_from_token, require_admin
from app.models.base import Household
from app.services.backup_service import BackupService
from app.schemas.backup import (
    BackupImportRequest,
    BackupImportResponse,
    BackupValidationResponse,
    RestoreResponse,
    RestoreStatusResponse,
)

settings = get_settings()
router = APIRouter(prefix="/backup", tags=["Backup & Restore"])
logger = logging.getLogger(__name__)

MAX_BACKUP_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/export")
async def export_backup(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Export all household data as a downloadable ZIP archive."""
    service = BackupService(db)
    try:
        zip_bytes = await service.export_backup(household.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Backup export failed: %s", exc)
        raise HTTPException(status_code=500, detail="Backup export failed")

    household_slug = household.name.replace(" ", "_").lower()
    filename = f"backup_{household_slug}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/validate", response_model=BackupValidationResponse)
async def validate_backup(
    file: UploadFile = File(...),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Validate a backup archive and stage it for import."""
    # Save uploaded file to a temp location (bypassing storage validation for ZIP)
    staging_dir = Path(settings.STORAGE_PATH) / "backup-upload"
    staging_dir.mkdir(parents=True, exist_ok=True)
    temp_path = staging_dir / f"{uuid.uuid4()}.zip"

    content = await file.read()
    if len(content) > MAX_BACKUP_SIZE:
        raise HTTPException(status_code=413, detail="Backup file too large (max 500 MB)")
    temp_path.write_bytes(content)

    try:
        service = BackupService(db)
        result = service.validate_backup(temp_path)
        return result
    except Exception as exc:
        logger.error("Backup validation failed: %s", exc)
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=500, detail="Backup validation failed")


@router.post("/import", response_model=BackupImportResponse)
async def import_backup(
    request: BackupImportRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Import a previously validated backup archive."""
    service = BackupService(db)
    try:
        result = await service.import_backup(household.id, request.validation_id, request.mode)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Backup import failed: %s", exc)
        raise HTTPException(status_code=500, detail="Backup import failed")


@router.delete("/staging/{validation_id}", status_code=204)
async def cleanup_staging(
    validation_id: str,
    household: Household = Depends(get_household_from_token),
):
    """Clean up a staged backup file."""
    staging_root = (Path(settings.STORAGE_PATH) / "backup-staging").resolve()
    staged_path = (staging_root / validation_id).resolve()
    if not staged_path.is_relative_to(staging_root):
        raise HTTPException(status_code=400, detail="Invalid validation ID")
    if staged_path.exists():
        staged_path.unlink()


# ── On-server compressed backups (Data tab) ─────────────────────────────────
# These produce/consume the server-wide disaster-recovery archives written by
# jobs.run_backup_now() (data/backups/backup_*.tar.gz), distinct from the
# household-scoped export/import ZIP above.

# Strict pattern: backup_YYYYMMDD_HHMMSS.tar.gz — no room for path traversal.
_ARCHIVE_RE = re.compile(r"^backup_\d{8}_\d{6}\.tar\.gz$")


def _resolve_archive(name: str) -> Path:
    """Validate *name* and return its absolute path within the backup dir."""
    if not _ARCHIVE_RE.match(name):
        raise HTTPException(status_code=400, detail="Invalid archive name")
    backup_root = jobs.BACKUP_DIR.resolve()
    path = (jobs.BACKUP_DIR / name).resolve()
    try:
        path.relative_to(backup_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid archive name")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archive not found")
    return path


@router.get("/status")
async def backup_status(_user=Depends(get_current_user)):
    """Storage overview: attachments / DB / backups sizes, disk, last run."""
    return jobs.get_backup_status()


@router.get("/archives")
async def list_backup_archives(_user=Depends(get_current_user)):
    """List on-server backup archives (newest first)."""
    return {"archives": jobs.list_backup_archives()}


@router.post("/run")
async def run_backup(_user=Depends(require_admin)):
    """Create a compressed backup archive now (admin)."""
    result = await jobs.run_backup_now()
    if result is None:
        raise HTTPException(status_code=500, detail="Backup failed — see server logs")
    return result


@router.get("/archives/{name}")
async def download_backup_archive(name: str, _user=Depends(require_admin)):
    """Download a backup archive (admin — contains all data)."""
    path = _resolve_archive(name)
    return FileResponse(
        str(path),
        media_type="application/gzip",
        filename=name,
    )


@router.delete("/archives/{name}", status_code=204)
async def delete_backup_archive(name: str, _user=Depends(require_admin)):
    """Delete a backup archive (admin)."""
    path = _resolve_archive(name)
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete archive: {exc}")


@router.post("/archives/{name}/restore", response_model=RestoreResponse, status_code=202)
async def restore_backup_archive(name: str, _user=Depends(require_admin)):
    """Restore a disaster-recovery ``backup_*.tar.gz`` archive (admin).

    Swapping a live SQLite snapshot requires a service restart, which the
    unprivileged ``health-manager`` service can't perform. So this endpoint only
    *validates* the archive and drops its name into a flag file watched by the
    root ``health-manager-restore.path`` unit, which does the actual
    stop → swap → start. Returns immediately (202); the client polls
    ``/restore/status`` (or ``/backup/status``) until the service is back.
    """
    archive = _resolve_archive(name)  # 400 on bad name, 404 if missing

    if jobs.is_restore_in_progress():
        raise HTTPException(status_code=409, detail="A restore is already in progress")

    jobs.trigger_restore(archive.name)
    logger.info(
        "Restore requested by admin '%s' for archive %s",
        getattr(_user, "username", "?"),
        archive.name,
    )
    return RestoreResponse(status="restore_started", archive=archive.name)


@router.get("/restore/status", response_model=RestoreStatusResponse)
async def restore_status(_user=Depends(get_current_user)):
    """Report whether a restore is in progress plus the last outcome marker."""
    return RestoreStatusResponse(
        in_progress=jobs.is_restore_in_progress(),
        last=jobs.read_restore_result(),
    )
