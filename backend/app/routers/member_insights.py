"""Member AI insights router — generate and retrieve health insights."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.core.sse import make_sse_stream
from app.models.ai import AIInsight
from app.models.base import Household
from app.prompts.insight_prompts import BRIEF_INSIGHT_PROMPT, COMPREHENSIVE_INSIGHT_PROMPT
from app.schemas.insight_serializers import serialize_insight_payload
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["AI Insights"])


def _prompt_for(mode: str) -> str:
    """Select the insight prompt for the requested generation mode."""
    return BRIEF_INSIGHT_PROMPT if mode == "brief" else COMPREHENSIVE_INSIGHT_PROMPT


@router.post("/{member_id}/generate-insights")
async def generate_member_insights(
    member_id: UUID,
    mode: str = "comprehensive",
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate comprehensive AI health insights for a member."""
    from app.services.ai_service import AIService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    ai_service = AIService(db, household_id=household.id)
    prompt = _prompt_for(mode)
    try:
        insight = await ai_service.generate_insight(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
            mode=mode,
        )
        await db.commit()
    except Exception as exc:
        logger.error("Comprehensive insight generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI service unavailable. Please try again.")

    try:
        from app.services.insight_service import spawn_insight_verification_task

        context = await ai_service._build_member_context(member_id, comprehensive=True)
        spawn_insight_verification_task(insight.id, context)
    except Exception:
        logger.debug("Insight verification skipped")

    return serialize_insight_payload(insight)


@router.post("/{member_id}/generate-insights/stream")
async def generate_member_insights_stream(
    member_id: UUID,
    mode: str = "comprehensive",
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Stream comprehensive AI health insight generation with real-time progress (SSE)."""
    from app.services.ai_service import AIService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    ai_service = AIService(db, household_id=household.id)
    prompt = _prompt_for(mode)

    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
            mode=mode,
        ),
        db,
    )


@router.get("/{member_id}/latest-insight")
async def get_latest_insight(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest persisted AI health insight, or auto-generate one."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.prompt.notlike("__drug_interactions__%"),
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing:
        return serialize_insight_payload(existing)

    from app.services.ai_service import AIService

    ai_service = AIService(db, household_id=household.id)
    prompt = COMPREHENSIVE_INSIGHT_PROMPT
    try:
        insight = await ai_service.generate_insight(
            prompt=prompt, member_id=member_id, comprehensive=True
        )
        await db.commit()
    except Exception as exc:
        logger.error("Auto insight generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI service unavailable. Please try again.")

    return serialize_insight_payload(insight)
