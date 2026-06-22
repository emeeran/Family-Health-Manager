"""Database integrity check + maintenance router (Data tab)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core import jobs
from app.core.deps import get_current_user, require_admin
from app.schemas.database import IntegrityReport, RepairRequest, RepairResponse
from app.services.db_maintenance import check_integrity, repair

router = APIRouter(prefix="/database", tags=["Database"])
logger = logging.getLogger(__name__)


@router.get("/integrity", response_model=IntegrityReport)
async def get_integrity(_user=Depends(get_current_user)):
    """Read-only structural integrity scan. Safe for any authenticated user.

    SQLite: PRAGMA integrity_check / quick_check / foreign_key_check + per-table
    counts + page stats. PostgreSQL: per-table counts + DB size (the server
    guarantees structural integrity).
    """
    return await check_integrity()


@router.post("/repair", response_model=RepairResponse)
async def run_repair(
    request: RepairRequest,
    _user=Depends(require_admin),
):
    """Run a maintenance operation (admin): checkpoint | reindex | vacuum.

    Refused with 409 if a disaster-recovery restore is in flight — a restore
    swaps the DB file out from under us.
    """
    if jobs.is_restore_in_progress():
        raise HTTPException(status_code=409, detail="A restore is in progress")
    logger.info(
        "Database repair '%s' requested by admin '%s'",
        request.operation,
        getattr(_user, "username", "?"),
    )
    return await repair(request.operation)
