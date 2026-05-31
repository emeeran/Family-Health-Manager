"""Preventive care router — age- and condition-based recommendations and reminders."""
import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household, ReminderType, ScheduleType
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Preventive Care"])


class PreventiveReminderRequest(BaseModel):
    """Validated request body for preventive-reminders."""
    title: str = Field("Preventive care reminder", max_length=200)
    description: str = Field("", max_length=1000)
    due_interval_months: int = Field(12, ge=1, le=120)


@router.get("/{member_id}/preventive-recommendations")
async def get_preventive_recommendations(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get age- and condition-based preventive care recommendations."""
    from app.services.preventive_care_service import PreventiveCareService

    service = MemberService(db)
    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    care_service = PreventiveCareService(db)
    recommendations = await care_service.generate_recommendations(member)
    return {"recommendations": recommendations}


@router.post("/{member_id}/preventive-reminders")
async def create_preventive_reminder(
    member_id: UUID,
    body: PreventiveReminderRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Convert a preventive care recommendation into a reminder."""
    from app.services.reminder_service import ReminderService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    title = body.title
    description = body.description
    months = body.due_interval_months
    due_date = datetime.now() + timedelta(days=months * 30)

    reminder_svc = ReminderService(db)
    reminder = await reminder_svc.create_reminder(
        household_id=household.id,
        reminder_type=ReminderType.CHECK_UP,
        title=title,
        description=description,
        schedule_type=ScheduleType.ONCE,
        start_datetime=due_date,
        member_id=member_id,
    )
    return {"id": str(reminder.id), "title": title, "due_date": due_date.isoformat()}
