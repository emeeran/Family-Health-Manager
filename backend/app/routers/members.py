"""Family member CRUD router — core create/read/update/delete operations."""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import FamilyMember, HealthRecord, RecordType, Household
from app.schemas.family_member import (
    FamilyMemberCreate,
    FamilyMemberUpdate,
    FamilyMemberResponse,
)
from app.services.member_service import MemberService
from app.services.medication_service import MedicationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Family Members"])


@router.get("", response_model=list[FamilyMemberResponse])
async def list_members(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    is_active: bool | None = Query(True),
):
    """List all family members in household."""
    cache_key = f"members:{household.id}:{is_active}"
    cached = await cache.get_async(cache_key)
    if cached is not None:
        return cached

    service = MemberService(db)
    members = await service.list_members(household.id, is_active)
    await cache.set_async(cache_key, members, ttl=120)
    return members


@router.post("", status_code=201, response_model=FamilyMemberResponse)
async def create_member(
    request: FamilyMemberCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Add a new family member with medical history questionnaire."""
    service = MemberService(db)

    member = await service.create_member(
        household_id=household.id,
        first_name=request.first_name,
        last_name=request.last_name,
        date_of_birth=request.date_of_birth,
        gender=request.gender,
        relationship=request.relationship,
        medical_history=request.medical_history,
        allergies=[a.model_dump() for a in request.allergies] if request.allergies else None,
        emergency_contact_name=request.emergency_contact_name,
        emergency_contact_phone=request.emergency_contact_phone,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
        notes=request.notes,
    )
    await cache.invalidate_async(f"members:{household.id}")
    await cache.invalidate_async(f"dashboard_summary:{household.id}")
    return member


@router.get("/batch-scores")
async def get_batch_scores(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return dashboard summary scores for ALL active members in one call.

    Eliminates the N+1 pattern of calling /members/{id}/dashboard per member.
    Uses aggregate queries instead of loading full dashboards.
    """
    members_result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.household_id == household.id,
            FamilyMember.is_active.is_(True),
        )
    )
    members = list(members_result.scalars().all())

    if not members:
        return []

    member_ids = [m.id for m in members]

    counts_result = await db.execute(
        select(
            HealthRecord.family_member_id,
            func.count().label("total_records"),
        )
        .where(
            HealthRecord.family_member_id.in_(member_ids),
            HealthRecord.is_deleted.is_(False),
        )
        .group_by(HealthRecord.family_member_id)
    )
    record_counts = {row[0]: row[1] for row in counts_result.all()}

    latest_result = await db.execute(
        select(
            HealthRecord.family_member_id,
            func.max(HealthRecord.record_date).label("latest_date"),
        )
        .where(
            HealthRecord.family_member_id.in_(member_ids),
            HealthRecord.is_deleted.is_(False),
        )
        .group_by(HealthRecord.family_member_id)
    )
    latest_dates = {row[0]: row[1] for row in latest_result.all()}

    med_result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.family_member_id.in_(member_ids),
            HealthRecord.record_type == RecordType.DOCTOR_VISIT,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
    )
    med_records = list(med_result.scalars().all())

    med_counts = MedicationService.count_medications_from_records(med_records)

    return [
        {
            "member_id": str(m.id),
            "first_name": m.first_name,
            "last_name": m.last_name,
            "total_records": record_counts.get(m.id, 0),
            "latest_record_date": (d.isoformat() if (d := latest_dates.get(m.id)) is not None else None),
            "active_medications_count": med_counts.get(str(m.id), 0),
        }
        for m in members
    ]


@router.get("/{member_id}/detail")
async def get_member_detail(
    member_id: str,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated member detail — single call replacing 8 parallel API calls."""
    from uuid import UUID

    member_id = UUID(str(member_id))
    service = MemberService(db)
    try:
        return await service.get_member_detail(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")


@router.get("/{member_id}", response_model=FamilyMemberResponse)
async def get_member(
    member_id,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get family member details."""
    from uuid import UUID

    member_id = UUID(str(member_id))
    service = MemberService(db)
    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.put("/{member_id}", response_model=FamilyMemberResponse)
async def update_member(
    member_id,
    request: FamilyMemberUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update family member profile."""
    from uuid import UUID

    member_id = UUID(str(member_id))
    service = MemberService(db)

    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    update_data = request.model_dump(exclude_unset=True)

    if "allergies" in update_data:
        allergies_list = update_data.pop("allergies")
        if allergies_list is not None:
            update_data["allergies_json"] = json.dumps(allergies_list)
        else:
            update_data["allergies_json"] = None

    member = await service.update_member(member_id, **update_data)
    await cache.invalidate_async(f"members:{household.id}")
    await cache.invalidate_async(f"dashboard_summary:{household.id}")
    return member


@router.delete("/{member_id}", status_code=204)
async def delete_member(
    member_id,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a family member."""
    from uuid import UUID

    member_id = UUID(str(member_id))
    service = MemberService(db)

    try:
        await service.soft_delete_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    await cache.invalidate_async(f"members:{household.id}")
    await cache.invalidate_async(f"household_records:{household.id}")
    await cache.invalidate_async(f"dashboard_summary:{household.id}")
