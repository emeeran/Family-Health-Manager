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
from app.services.drug_info import DrugInfoService
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Drug Interactions"])


async def _generate_interactions(
    db: AsyncSession, household: Household, medications: list[dict]
) -> list[dict]:
    """DrugBank-first, AI-fallback interactions, each tagged with ``source``.

    DrugBank (authoritative, when a key is configured) is tried first. If it
    yields nothing — no key, meds unresolvable, or genuinely no interactions —
    we fall back to the existing AI checker so behavior is unchanged for
    Ollama-only installs. Every returned interaction carries ``source`` =
    ``"drugbank"`` or ``"ai"`` so the UI can badge it.
    """
    interactions = await DrugInfoService(db).ddi(medications)

    if not interactions:
        from app.services.ai_service import AIService

        try:
            ai_service = AIService(db, household_id=household.id)
            interactions = await ai_service.check_drug_interactions(medications)
        except Exception as exc:
            logger.error("Drug interaction check failed: %s", exc)
            interactions = []

    for ix in interactions:
        if isinstance(ix, dict) and not ix.get("source"):
            ix["source"] = "ai"
    return interactions


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
                return {
                    "interactions": interactions,
                    "medications_checked": len(medications),
                    "cached_at": cached.generated_at.isoformat(),
                }
        except (json.JSONDecodeError, ValueError):
            pass

    interactions = await _generate_interactions(db, household, medications)
    try:
        cached_insight = AIInsight(
            prompt=f"__drug_interactions__{member_id}",
            response=json.dumps(interactions),
            provider_used="auto",
        )
        db.add(cached_insight)
        await db.commit()
    except Exception as exc:
        logger.error("Failed to cache drug interactions: %s", exc)

    return {
        "interactions": interactions,
        "medications_checked": len(medications),
        "cached_at": None,
    }


@router.get("/{member_id}/drug-interactions")
async def get_drug_interactions(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Check drug interactions between active medications (DrugBank → AI)."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medications = await service.get_active_medications(member_id)

    if len(medications) < 2:
        return {"interactions": [], "medications_checked": len(medications)}

    interactions = await _generate_interactions(db, household, medications)

    return {
        "interactions": interactions,
        "medications_checked": len(medications),
    }
