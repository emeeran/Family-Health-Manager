"""Audit log router."""
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.audit_service import AuditService
from app.schemas.audit import AuditLogResponse
from app.models.base import Household

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
):
    """List audit log entries."""
    service = AuditService(db)
    logs = await service.list_audit_logs(
        household.primary_user_id, action, resource_type, date_from, date_to
    )
    return logs
