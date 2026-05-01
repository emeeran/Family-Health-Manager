"""Medication tracking router — active medications and refill reminders."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household
from app.services.medication_service import MedicationService
from app.services.member_service import MemberService

router = APIRouter(prefix="/members/{member_id}/medications", tags=["Medications"])


@router.get("/active")
async def get_active_medications(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get currently active medications for a family member."""
    # Verify member belongs to household
    member_service = MemberService(db)
    try:
        await member_service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medication_service = MedicationService(db)
    medications = await medication_service.get_active_medications(member_id)
    return {"items": medications}


@router.get("/refill-reminders")
async def get_refill_reminders(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get medications that need refill within the next 7 days."""
    # Verify member belongs to household
    member_service = MemberService(db)
    try:
        await member_service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medication_service = MedicationService(db)
    reminders = await medication_service.get_refill_reminders(member_id)
    return {"items": reminders}
