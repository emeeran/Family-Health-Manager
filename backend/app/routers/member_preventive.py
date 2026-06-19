"""Preventive care router — age- and condition-based recommendations and reminders."""

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token, require_member_in_household
from app.models.base import FamilyMember, Household, ReminderType, ScheduleType

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
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Get age- and condition-based preventive care recommendations."""
    from app.services.preventive_care_service import PreventiveCareService

    care_service = PreventiveCareService(db)
    recommendations = await care_service.generate_recommendations(member)
    return {"recommendations": recommendations}


@router.post("/{member_id}/preventive-reminders")
async def create_preventive_reminder(
    member_id: UUID,
    body: PreventiveReminderRequest,
    household: Household = Depends(get_household_from_token),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Convert a preventive care recommendation into a reminder."""
    from app.services.reminder_service import ReminderService

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
