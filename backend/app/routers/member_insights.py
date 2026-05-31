"""Member AI insights router — generate and retrieve health insights."""
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.core.sse import make_sse_stream
from app.models.ai import AIInsight
from app.models.base import Household
from app.prompts.insight_prompts import COMPREHENSIVE_INSIGHT_PROMPT
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["AI Insights"])


@router.post("/{member_id}/generate-insights")
async def generate_member_insights(
    member_id: UUID,
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

    ai_service = AIService(db)
    prompt = COMPREHENSIVE_INSIGHT_PROMPT
    try:
        insight = await ai_service.generate_insight(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
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

    return {
        "id": str(insight.id),
        "response": insight.response,
        "provider_used": insight.provider_used,
        "generated_at": insight.generated_at.isoformat(),
        "verification": {
            "status": insight.verification_status,
            "claims_checked": insight.verification_claims_checked,
            "verifier_provider": insight.verification_verifier,
            "summary": insight.verification_summary,
            "warnings": json.loads(insight.verification_warnings_json) if insight.verification_warnings_json else None,
            "verified_at": insight.verification_at.isoformat() if insight.verification_at else None,
        } if insight.verification_status != "pending" or insight.verification_at else {"status": "pending"},
    }


@router.post("/{member_id}/generate-insights/stream")
async def generate_member_insights_stream(
    member_id: UUID,
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

    ai_service = AIService(db)
    prompt = COMPREHENSIVE_INSIGHT_PROMPT

    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
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
        return {
            "id": str(existing.id),
            "response": existing.response,
            "provider_used": existing.provider_used,
            "generated_at": existing.generated_at.isoformat(),
            "verification": {
                "status": existing.verification_status,
                "claims_checked": existing.verification_claims_checked,
                "verifier_provider": existing.verification_verifier,
                "summary": existing.verification_summary,
                "warnings": json.loads(existing.verification_warnings_json) if existing.verification_warnings_json else None,
                "verified_at": existing.verification_at.isoformat() if existing.verification_at else None,
            } if existing.verification_status != "pending" or existing.verification_at else {"status": "pending" if (datetime.now(timezone.utc) - existing.generated_at.replace(tzinfo=timezone.utc)).total_seconds() < 300 else "unverifiable"},
        }

    from app.services.ai_service import AIService
    ai_service = AIService(db)
    prompt = COMPREHENSIVE_INSIGHT_PROMPT
    try:
        insight = await ai_service.generate_insight(
            prompt=prompt, member_id=member_id, comprehensive=True
        )
        await db.commit()
    except Exception as exc:
        logger.error("Auto insight generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI service unavailable. Please try again.")

    return {
        "id": str(insight.id),
        "response": insight.response,
        "provider_used": insight.provider_used,
        "generated_at": insight.generated_at.isoformat(),
        "verification": {"status": "pending"},
    }
