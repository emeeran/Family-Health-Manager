"""Vaccination router."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.member_service import MemberService
from app.schemas.vaccination import VaccinationCreate, VaccinationUpdate, VaccinationResponse
from app.models.base import Household, Vaccination

router = APIRouter(prefix="/members/{member_id}/vaccinations", tags=["Vaccinations"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[VaccinationResponse])
async def list_vaccinations(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List all vaccinations for a member."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    result = await db.execute(
        select(Vaccination)
        .where(Vaccination.family_member_id == member_id)
        .order_by(Vaccination.date_administered.desc())
    )
    return list(result.scalars().all())


@router.post("", status_code=201, response_model=VaccinationResponse)
async def create_vaccination(
    member_id: UUID,
    request: VaccinationCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Add a vaccination record."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    vaccination = Vaccination(
        family_member_id=member_id,
        name=request.name,
        date_administered=request.date_administered,
        booster_due_date=request.booster_due_date,
        notes=request.notes,
    )
    db.add(vaccination)
    await db.flush()
    return vaccination


@router.put("/{vaccination_id}", response_model=VaccinationResponse)
async def update_vaccination(
    member_id: UUID,
    vaccination_id: UUID,
    request: VaccinationUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update a vaccination record."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    result = await db.execute(
        select(Vaccination).where(
            Vaccination.id == vaccination_id,
            Vaccination.family_member_id == member_id,
        )
    )
    vaccination = result.scalar_one_or_none()
    if not vaccination:
        raise HTTPException(status_code=404, detail="Vaccination not found")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(vaccination, key, value)
    await db.flush()
    return vaccination


@router.delete("/{vaccination_id}", status_code=204)
async def delete_vaccination(
    member_id: UUID,
    vaccination_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a vaccination record."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    result = await db.execute(
        select(Vaccination).where(
            Vaccination.id == vaccination_id,
            Vaccination.family_member_id == member_id,
        )
    )
    vaccination = result.scalar_one_or_none()
    if not vaccination:
        raise HTTPException(status_code=404, detail="Vaccination not found")

    await db.delete(vaccination)
