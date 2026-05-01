"""Household router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.household_service import HouseholdService
from app.schemas.household import HouseholdResponse, HouseholdUpdate
from app.schemas.health_record import HealthRecordResponse
from app.models.base import Household, FamilyMember
from app.models.record import HealthRecord
from app.core.cache import cache

router = APIRouter(prefix="/household", tags=["Household"])


@router.get("", response_model=HouseholdResponse)
async def get_household(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get current household details."""
    service = HouseholdService(db)
    household = await service.get_household(household.id)
    return household


@router.put("", response_model=HouseholdResponse)
async def update_household(
    request: HouseholdUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update household name."""
    service = HouseholdService(db)

    if not request.name:
        raise HTTPException(status_code=400, detail="Name is required")

    household = await service.update_household(household.id, request.name)
    return household


@router.get("/records", response_model=list[HealthRecordResponse])
async def list_household_records(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, le=500),
):
    """List records for all members in the household in a single query."""
    cache_key = f"household_records:{household.id}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    stmt = (
        select(HealthRecord)
        .options(joinedload(HealthRecord.provider), joinedload(HealthRecord.attachments))
        .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
        .where(
            FamilyMember.household_id == household.id,
            FamilyMember.is_active.is_(True),
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        .limit(limit)
    )
    rows = await db.execute(stmt)
    records = list(rows.scalars().unique().all())
    cache.set(cache_key, records, ttl=60)
    return records


@router.get("/records/search", response_model=list[HealthRecordResponse])
async def search_household_records(
    q: str = Query("", min_length=1),
    limit: int = Query(12, le=50),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Search records across all household members by diagnosis, clinical_data, or provider name."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    stmt = (
        select(HealthRecord)
        .options(joinedload(HealthRecord.provider), joinedload(HealthRecord.attachments))
        .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
        .where(
            FamilyMember.household_id == household.id,
            FamilyMember.is_active.is_(True),
            HealthRecord.is_deleted.is_(False),
            or_(
                HealthRecord.diagnosis.ilike(pattern, escape="\\"),
                HealthRecord.clinical_data.ilike(pattern, escape="\\"),
                HealthRecord.prescription_text.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        .limit(limit)
    )
    rows = await db.execute(stmt)
    return list(rows.scalars().unique().all())
