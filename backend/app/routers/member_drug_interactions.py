"""Drug interaction checking router — AI-powered medication interaction analysis."""
import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.ai import AIInsight
from app.models.base import Household
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Drug Interactions"])


@router.get("/{member_id}/latest-drug-interactions")
async def get_latest_drug_interactions(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return cached drug interactions, or auto-generate if none/stale (>24h)."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medications = await service.get_active_medications(member_id)
    if len(medications) < 2:
        return {"interactions": [], "medications_checked": len(medications)}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cache_key = f"__drug_interactions__{member_id}"
    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.prompt == cache_key,
            AIInsight.generated_at >= cutoff,
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    cached = result.scalar_one_or_none()

    if cached:
        try:
            interactions = json.loads(cached.response)
            if isinstance(interactions, list):
                return {"interactions": interactions, "medications_checked": len(medications)}
        except (json.JSONDecodeError, ValueError):
            pass

    from app.services.ai_service import AIService
    ai_service = AIService(db)
    try:
        interactions = await ai_service.check_drug_interactions(medications)
        cached_insight = AIInsight(
            prompt=f"__drug_interactions__{member_id}",
            response=json.dumps(interactions),
            provider_used="auto",
        )
        db.add(cached_insight)
        await db.commit()
    except Exception as exc:
        logger.error("Drug interaction check failed: %s", exc)
        interactions = []

    return {"interactions": interactions, "medications_checked": len(medications)}


@router.get("/{member_id}/drug-interactions")
async def get_drug_interactions(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Check drug interactions between active medications using AI."""
    from app.services.ai_service import AIService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medications = await service.get_active_medications(member_id)

    if len(medications) < 2:
        return {"interactions": [], "medications_checked": len(medications)}

    try:
        ai_service = AIService(db)
        interactions = await ai_service.check_drug_interactions(medications)
    except Exception as exc:
        logger.error("Drug interaction check failed: %s", exc)
        interactions = []

    return {
        "interactions": interactions,
        "medications_checked": len(medications),
    }
