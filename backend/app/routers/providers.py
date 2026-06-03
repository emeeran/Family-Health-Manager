"""Provider router."""
import json
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.provider_service import ProviderService
from app.schemas.provider import ProviderCreate, ProviderUpdate, ProviderResponse
from app.schemas.provider_assignment import ProviderAssignmentResponse
from app.schemas.health_record import HealthRecordResponse
from app.models.base import Household, Provider
from app.models.record import HealthRecord

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
            id=m["assignment_id"] or provider_id,
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


@router.get("/{provider_id}/records", response_model=list[HealthRecordResponse])
async def get_provider_records(
    provider_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """Get all health records from a specific provider."""
    service = ProviderService(db)
    try:
        await service.get_provider(household.id, provider_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")

    result = await db.execute(
        select(HealthRecord)
        .options(
            joinedload(HealthRecord.provider),
            joinedload(HealthRecord.attachments),
        )
        .where(
            HealthRecord.provider_id == provider_id,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
        .limit(limit)
        .offset(offset)
    )
    records = result.scalars().unique().all()
    return records


@router.get("/{provider_id}/stats")
async def get_provider_stats(
    provider_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get stats for a provider: visit count, last visit, top diagnoses."""
    service = ProviderService(db)
    try:
        await service.get_provider(household.id, provider_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Total visits and last visit date
    result = await db.execute(
        select(
            func.count(HealthRecord.id),
            func.max(HealthRecord.record_date),
        ).where(
            HealthRecord.provider_id == provider_id,
            HealthRecord.is_deleted.is_(False),
        )
    )
    row = result.one()
    visit_count = row[0] or 0
    last_visit = row[1]

    # Top diagnoses and most prescribed medications
    records_result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.provider_id == provider_id,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
        .limit(200)
    )
    records = records_result.scalars().all()

    diagnoses: Counter[str] = Counter()
    medicines: Counter[str] = Counter()
    for r in records:
        if r.diagnosis and r.diagnosis.strip():
            diagnoses[r.diagnosis.strip()] += 1
        if r.clinical_data:
            try:
                parsed = json.loads(r.clinical_data)
                if isinstance(parsed, dict) and parsed.get("_type") == "structured":
                    for rx in parsed.get("prescriptions", []):
                        med = (rx.get("medicine") or "").strip()
                        if med:
                            medicines[med] += 1
            except (json.JSONDecodeError, ValueError):
                pass

    return {
        "visit_count": visit_count,
        "last_visit": last_visit.isoformat() if last_visit else None,
        "top_diagnoses": [
            {"diagnosis": d, "count": c}
            for d, c in diagnoses.most_common(10)
        ],
        "most_prescribed": [
            {"medicine": m, "count": c}
            for m, c in medicines.most_common(10)
        ],
    }


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
