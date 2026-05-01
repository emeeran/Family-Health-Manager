"""Provider assignment router."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.provider_service import ProviderService
from app.services.member_service import MemberService
from pydantic import BaseModel, Field
from app.schemas.provider_assignment import ProviderAssignmentCreate, ProviderAssignmentResponse
from app.models.base import Household, Provider
from sqlalchemy import select

router = APIRouter(prefix="/members/{member_id}/providers", tags=["Provider Assignments"])


@router.get("", response_model=list[ProviderAssignmentResponse])
async def list_member_providers(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List providers assigned to a member."""
    service = ProviderService(db)

    try:
        await MemberService(db).get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    rows = await service.get_member_providers(member_id)
    return [
        ProviderAssignmentResponse(
            id=a.id,
            provider_id=a.provider_id,
            provider_name=p.name,
            family_member_id=a.family_member_id,
            family_member_name=f"{m.first_name} {m.last_name}",
            uhid=a.uhid,
            created_at=a.created_at,
        )
        for a, p, m in rows
    ]


@router.post("", status_code=201, response_model=ProviderAssignmentResponse)
async def assign_provider(
    member_id: UUID,
    request: ProviderAssignmentCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Assign a provider to a member."""
    service = ProviderService(db)

    try:
        member = await MemberService(db).get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    try:
        assignment = await service.assign_provider_to_member(
            provider_id=request.provider_id,
            member_id=member_id,
            uhid=request.uhid,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Assignment failed")

    # Look up provider name for the response
    result = await db.execute(select(Provider).where(Provider.id == request.provider_id))
    provider = result.scalar_one_or_none()

    return ProviderAssignmentResponse(
        id=assignment.id,
        provider_id=assignment.provider_id,
        provider_name=provider.name if provider else "",
        family_member_id=assignment.family_member_id,
        family_member_name=f"{member.first_name} {member.last_name}",
        uhid=assignment.uhid,
        created_at=assignment.created_at,
    )


@router.delete("/{assignment_id}", status_code=204)
async def remove_assignment(
    member_id: UUID,
    assignment_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Remove provider assignment."""
    service = ProviderService(db)
    await service.remove_provider_assignment(assignment_id, household.id, member_id)


class UpdateUhidRequest(BaseModel):
    uhid: str | None = Field(None, max_length=50)


@router.patch("/{assignment_id}", response_model=ProviderAssignmentResponse)
async def update_uhid(
    member_id: UUID,
    assignment_id: UUID,
    request: UpdateUhidRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update UHID on a provider assignment."""
    service = ProviderService(db)
    try:
        assignment = await service.update_assignment_uhid(assignment_id, request.uhid)
    except ValueError:
        raise HTTPException(status_code=404, detail="Assignment not found")

    provider = await db.get(Provider, assignment.provider_id)
    member = await MemberService(db).get_member(household.id, member_id)
    return ProviderAssignmentResponse(
        id=assignment.id,
        provider_id=assignment.provider_id,
        provider_name=provider.name if provider else "",
        family_member_id=assignment.family_member_id,
        family_member_name=f"{member.first_name} {member.last_name}",
        uhid=assignment.uhid,
        created_at=assignment.created_at,
    )
