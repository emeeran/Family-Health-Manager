"""Reminder router."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.reminder_service import ReminderService
from app.services.member_service import MemberService
from app.schemas.reminder import ReminderCreate, ReminderUpdate, ReminderResponse
from app.models.base import Household, ReminderType

router = APIRouter(prefix="/reminders", tags=["Reminders"])


@router.get("", response_model=list[ReminderResponse])
async def list_reminders(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    reminder_type: ReminderType | None = None,
    is_active: bool | None = None,
    family_member_id: UUID | None = None,
):
    """List all reminders."""
    service = ReminderService(db)
    reminders = await service.list_reminders(
        household.id, reminder_type, is_active, family_member_id
    )
    return reminders


@router.post("", status_code=201, response_model=ReminderResponse)
async def create_reminder(
    request: ReminderCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Create a reminder."""
    service = ReminderService(db)

    if request.family_member_id:
        try:
            await MemberService(db).get_member(household.id, request.family_member_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Member not found")

    reminder = await service.create_reminder(
        household_id=household.id,
        reminder_type=request.reminder_type,
        title=request.title,
        description=request.description,
        schedule_type=request.schedule_type,
        schedule_interval=request.schedule_interval,
        start_datetime=request.start_datetime,
        end_datetime=request.end_datetime,
        member_id=request.family_member_id,
    )
    return reminder


@router.get("/{reminder_id}", response_model=ReminderResponse)
async def get_reminder(
    reminder_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get reminder details."""
    service = ReminderService(db)
    try:
        reminder = await service.get_reminder(household.id, reminder_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return reminder


@router.put("/{reminder_id}", response_model=ReminderResponse)
async def update_reminder(
    reminder_id: UUID,
    request: ReminderUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update reminder."""
    service = ReminderService(db)

    try:
        await service.get_reminder(household.id, reminder_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Reminder not found")

    update_data = request.model_dump(exclude_unset=True)
    reminder = await service.update_reminder(reminder_id, household.id, **update_data)
    return reminder


@router.delete("/{reminder_id}", status_code=204)
async def delete_reminder(
    reminder_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete reminder."""
    service = ReminderService(db)

    try:
        await service.delete_reminder(household.id, reminder_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Reminder not found")
