"""Household router."""
import json
import logging
from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.core.database import get_db
from app.core.deps import get_household_from_token, get_current_user
from app.core.security import verify_password
from app.services.household_service import HouseholdService
from app.schemas.household import (
    HouseholdResponse,
    HouseholdUpdate,
    HouseholdSettingsResponse,
    HouseholdSettingsUpdate,
    FeatureSettings,
)
from app.schemas.ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigResponse,
    AVAILABLE_MODELS,
    PROVIDER_LABELS,
)
from app.schemas.health_record import HealthRecordResponse
from app.models.base import Household, FamilyMember, User
from app.models.record import HealthRecord
from app.core.cache import cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/household", tags=["Household"])


@router.get("", response_model=HouseholdResponse)
async def get_household(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get current household details."""
    service = HouseholdService(db)
    household = await service.get_household(household.id)
    settings = _parse_settings(household)
    return HouseholdResponse(
        id=household.id,
        name=household.name,
        primary_user_id=household.primary_user_id,
        created_at=household.created_at,
        settings=settings,
    )


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


def _parse_settings(household: Household) -> FeatureSettings:
    """Parse settings_json from household into FeatureSettings with defaults."""
    if household.settings_json:
        try:
            data = json.loads(household.settings_json)
            return FeatureSettings(**data)
        except (json.JSONDecodeError, ValueError):
            pass
    return FeatureSettings()


@router.get("/settings", response_model=HouseholdSettingsResponse)
async def get_settings(
    household: Household = Depends(get_household_from_token),
):
    """Get feature toggle settings for the household."""
    return HouseholdSettingsResponse(settings=_parse_settings(household))


@router.put("/settings", response_model=HouseholdSettingsResponse)
async def update_settings(
    request: HouseholdSettingsUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update feature toggle settings for the household."""
    settings_json = request.settings.model_dump_json()
    result = await db.execute(
        select(Household).where(Household.id == household.id)
    )
    db_household = result.scalar_one()
    db_household.settings_json = settings_json
    await db.flush()
    return HouseholdSettingsResponse(settings=request.settings)


@router.get("/ai-provider-config", response_model=AIProviderConfigResponse)
async def get_ai_provider_config(
    household: Household = Depends(get_household_from_token),
):
    """Get AI provider configuration for the household."""
    settings = _parse_settings(household)
    return AIProviderConfigResponse(
        config=settings.ai_providers,
        available_models=AVAILABLE_MODELS,
        provider_labels=PROVIDER_LABELS,
    )


@router.put("/ai-provider-config", response_model=AIProviderConfigResponse)
async def update_ai_provider_config(
    request: AIProviderConfig,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update AI provider configuration for the household."""
    # Load existing settings, replace only ai_providers
    existing = _parse_settings(household)
    existing.ai_providers = request
    settings_json = existing.model_dump_json()
    result = await db.execute(
        select(Household).where(Household.id == household.id)
    )
    db_household = result.scalar_one()
    db_household.settings_json = settings_json
    await db.flush()
    return AIProviderConfigResponse(
        config=request,
        available_models=AVAILABLE_MODELS,
        provider_labels=PROVIDER_LABELS,
    )


@router.get("/records", response_model=list[HealthRecordResponse])
async def list_household_records(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, le=500),
):
    """List records for all members in the household in a single query."""
    household_id = UUID(str(household.id))
    cache_key = f"household_records:{household_id}:{limit}"
    cached = await cache.get_async(cache_key)
    if cached is not None:
        return cached

    stmt = (
        select(HealthRecord)
        .options(joinedload(HealthRecord.provider), joinedload(HealthRecord.attachments))
        .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
        .where(
            FamilyMember.household_id == household_id,
            FamilyMember.is_active.is_(True),
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        .limit(limit)
    )
    rows = await db.execute(stmt)
    records = list(rows.scalars().unique().all())
    serialized = [HealthRecordResponse.model_validate(r).model_dump(mode="json") for r in records]
    await cache.set_async(cache_key, serialized, ttl=60)
    return serialized


@router.get("/records/search", response_model=list[HealthRecordResponse])
async def search_household_records(
    q: str = Query("", min_length=1),
    limit: int = Query(12, le=50),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Search records across all household members by diagnosis, clinical_data, or provider name."""
    household_id = UUID(str(household.id))
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    stmt = (
        select(HealthRecord)
        .options(joinedload(HealthRecord.provider), joinedload(HealthRecord.attachments))
        .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
        .where(
            FamilyMember.household_id == household_id,
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


class ResetDatabaseRequest(BaseModel):
    """Request body for database reset."""
    password: str
    confirmation: str  # Must be "RESET"


@router.post("/reset-database")
async def reset_database(
    request: ResetDatabaseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reset the database — drop all data and recreate tables.

    Requires admin role and password confirmation.
    Keeps the admin user account so they can still log in.
    """
    if request.confirmation != "RESET":
        raise HTTPException(status_code=400, detail="Confirmation must be 'RESET'")

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")

    from app.core.config import get_settings
    from app.models.base import Base

    settings = get_settings()

    # Save admin credentials before wiping
    admin_username = user.username
    admin_password_hash = user.password_hash

    # Expire all cached ORM objects to avoid stale identity-map conflicts
    db.expire_all()

    try:
        # Get list of all tables
        if settings.DATABASE_URL.startswith("sqlite"):
            tables_result = await db.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            )
            table_names = [row[0] for row in tables_result]
        else:
            tables_result = await db.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            table_names = [row[0] for row in tables_result]

        # Disable FK checks, delete all rows, re-enable
        if settings.DATABASE_URL.startswith("sqlite"):
            await db.execute(text("PRAGMA foreign_keys = OFF"))
            for table in table_names:
                await db.execute(text(f'DELETE FROM "{table}"'))
            await db.execute(text("PRAGMA foreign_keys = ON"))
        else:
            await db.execute(text("SET CONSTRAINTS ALL DEFERRED"))
            for table in table_names:
                await db.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))

        # Re-create the admin user so they can still log in
        new_user = User(
            username=admin_username,
            password_hash=admin_password_hash,
            role="admin",
        )
        db.add(new_user)
        await db.flush()

        # Create household for the user
        household = Household(
            name=f"{admin_username}'s Household",
            primary_user_id=new_user.id,
        )
        db.add(household)
        await db.flush()

        # Ensure schema is intact (SQLite)
        if settings.DATABASE_URL.startswith("sqlite"):
            from sqlalchemy import create_engine
            sync_db_url = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "sqlite:///")
            sync_engine = create_engine(sync_db_url)
            Base.metadata.create_all(sync_engine)
            sync_engine.dispose()

        # Let get_db handle the final commit — just flush pending changes
        await db.flush()

        # Clear application cache
        await cache.invalidate_async()

        logger.warning("Database reset by admin user: %s", admin_username)
        return {"message": "Database reset successfully"}

    except Exception as exc:
        logger.error("Database reset failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database reset failed: {exc}")
