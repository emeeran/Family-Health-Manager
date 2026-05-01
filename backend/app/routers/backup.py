"""Backup and restore router."""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household
from app.services.backup_service import BackupService
from app.schemas.backup import BackupImportRequest, BackupImportResponse, BackupValidationResponse

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
