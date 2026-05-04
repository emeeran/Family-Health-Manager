"""Reports router — PDF health report downloads."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])
logger = logging.getLogger(__name__)


@router.get("/health-summary")
async def health_summary_report(
    member_id: UUID | None = Query(None),
    enhanced: bool = Query(True),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a health summary PDF."""
    service = ReportService(db)
    if enhanced and not member_id:
        pdf_bytes = await service.generate_enhanced_health_pdf(
            household_id=UUID(household.id),
        )
    else:
        pdf_bytes = await service.generate_health_summary_pdf(
            household_id=UUID(household.id),
            member_id=member_id,
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=health-summary.pdf"},
    )
