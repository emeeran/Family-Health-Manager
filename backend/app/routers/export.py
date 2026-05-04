"""Export router — CSV downloads for health data."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household
from app.services.export_service import ExportService

router = APIRouter(prefix="/export", tags=["Export"])
logger = logging.getLogger(__name__)


@router.get("/records")
async def export_records(
    member_id: UUID | None = Query(None),
    record_type: str | None = Query(None),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Export health records as CSV."""
    service = ExportService(db)
    csv_data = await service.export_records_csv(
        household_id=UUID(household.id),
        member_id=member_id,
        record_type=record_type,
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=health-records.csv"},
    )


@router.get("/medications")
async def export_medications(
    member_id: UUID | None = Query(None),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Export medications as CSV."""
    service = ExportService(db)
    csv_data = await service.export_medications_csv(
        household_id=UUID(household.id),
        member_id=member_id,
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=medications.csv"},
    )


@router.get("/lab-results")
async def export_lab_results(
    member_id: UUID | None = Query(None),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Export lab results as CSV."""
    service = ExportService(db)
    csv_data = await service.export_lab_results_csv(
        household_id=UUID(household.id),
        member_id=member_id,
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lab-results.csv"},
    )
