"""Health alerts router."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household
from app.models.health_alert import AlertSeverity
from app.services.health_alert_service import HealthAlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health-alerts", tags=["Health Alerts"])


@router.get("")
async def list_alerts(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    member_id: UUID | None = Query(None),
    severity: AlertSeverity | None = Query(None),
    dismissed: bool | None = Query(False),
):
    """List health alerts for the household."""
    service = HealthAlertService(db)
    alerts = await service.list_alerts(
        household_id=household.id,
        member_id=member_id,
        severity=severity,
        dismissed=dismissed,
    )
    return [
        {
            "id": a.id,
            "household_id": a.household_id,
            "family_member_id": a.family_member_id,
            "record_id": a.record_id,
            "alert_type": a.alert_type.value if hasattr(a.alert_type, "value") else a.alert_type,
            "severity": a.severity.value if hasattr(a.severity, "value") else a.severity,
            "title": a.title,
            "message": a.message,
            "test_name": a.test_name,
            "value": a.value,
            "reference": a.reference,
            "is_dismissed": a.is_dismissed,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.put("/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss a health alert."""
    service = HealthAlertService(db)
    try:
        alert = await service.dismiss_alert(alert_id, household_id=household.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"dismissed": True, "id": alert.id}


@router.get("/count")
async def get_alert_count(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get undismissed alert count for badge."""
    service = HealthAlertService(db)
    count = await service.get_undismissed_count(household.id)
    return {"count": count}
