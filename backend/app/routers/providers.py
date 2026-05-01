"""Provider router."""
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.provider_service import ProviderService
from app.schemas.provider import ProviderCreate, ProviderUpdate, ProviderResponse
from app.schemas.provider_assignment import ProviderAssignmentResponse
from app.models.base import Household, Provider

router = APIRouter(prefix="/providers", tags=["Providers"])


async def _enrich_with_members(
    service: ProviderService, providers: list[Provider]
) -> list[dict]:
    """Attach assigned_members to each provider for the response."""
    from app.schemas.provider import AssignedMember

    results = []
    for p in providers:
        member_list = await service.get_members_for_provider(p.id)
        results.append(
            ProviderResponse(
                id=p.id,
                household_id=p.household_id,
                name=p.name,
                speciality=p.speciality,
                phone=p.phone,
                address=p.address,
                created_at=p.created_at,
                assigned_members=[AssignedMember(**m) for m in member_list],
            )
        )
    return results


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    speciality: str | None = Query(None),
):
    """List all providers in household with their assigned members."""
    service = ProviderService(db)
    providers = await service.list_providers(household.id, speciality)
    return await _enrich_with_members(service, providers)


@router.post("", status_code=201, response_model=ProviderResponse)
async def create_provider(
    request: ProviderCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Create a new provider."""
    service = ProviderService(db)
    provider = await service.create_provider(
        household_id=household.id,
        name=request.name,
        speciality=request.speciality,
        phone=request.phone,
        address=request.address,
    )
    return ProviderResponse.model_validate(provider)


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get provider details with assigned members."""
    service = ProviderService(db)
    try:
        provider = await service.get_provider(household.id, provider_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")
    enriched = await _enrich_with_members(service, [provider])
    return enriched[0]


@router.get("/{provider_id}/members", response_model=list[ProviderAssignmentResponse])
async def get_provider_members(
    provider_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List all family members assigned to this provider with their UHIDs."""
    service = ProviderService(db)
    try:
        await service.get_provider(household.id, provider_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")

    member_list = await service.get_members_for_provider(provider_id)
    return [
        ProviderAssignmentResponse(
            id=provider_id,  # placeholder — no assignment ID when derived from records
            provider_id=provider_id,
            provider_name="",
            family_member_id=m["family_member_id"],
            family_member_name=m["family_member_name"],
            uhid=m["uhid"],
            created_at=datetime.now(timezone.utc),
        )
        for m in member_list
    ]


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: UUID,
    request: ProviderUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update provider details."""
    service = ProviderService(db)
    try:
        await service.get_provider(household.id, provider_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")

    update_data = request.model_dump(exclude_unset=True)
    provider = await service.update_provider(provider_id, **update_data)
    enriched = await _enrich_with_members(service, [provider])
    return enriched[0]


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a provider."""
    service = ProviderService(db)
    try:
        await service.delete_provider(household.id, provider_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")
