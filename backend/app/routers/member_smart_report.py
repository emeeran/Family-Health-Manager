"""Smart Report router — generate and retrieve comprehensive health insight per member."""
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
from app.prompts.insight_prompts import SMART_REPORT_PROMPT
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Smart Report"])


async def _verify_member(household_id, member_id: UUID, db: AsyncSession):
    service = MemberService(db)
    try:
        return await service.get_member(household_id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")


def _build_smart_report_prompt(member_id: UUID) -> str:
    return f"__smartreport__{member_id}__\n\n{SMART_REPORT_PROMPT}"


@router.post("/{member_id}/smart-report")
async def generate_smart_report(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate a Smart Report (non-streaming)."""
    from app.services.ai_service import AIService

    await _verify_member(household.id, member_id, db)
    prompt = _build_smart_report_prompt(member_id)

    ai_service = AIService(db, household_id=household.id)
    try:
        insight = await ai_service.generate_insight(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
        )
        await db.commit()
    except Exception as exc:
        logger.error("Smart Report generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI service unavailable. Please try again.")

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


@router.get("/{member_id}/smart-report/latest")
async def get_latest_smart_report(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest persisted Smart Report, or null."""
    await _verify_member(household.id, member_id, db)

    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.prompt.like(f"__smartreport__{member_id}__%"),
            AIInsight.health_record_id.is_(None),
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        return {"report": None}

    return {
        "report": {
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
            } if insight.verification_status != "pending" or insight.verification_at else {"status": "pending" if (datetime.now(timezone.utc) - insight.generated_at.replace(tzinfo=timezone.utc)).total_seconds() < 300 else "unverifiable"},
        },
    }


@router.post("/{member_id}/smart-report/stream")
async def generate_smart_report_stream(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Stream Smart Report generation with real-time progress (SSE)."""
    from app.services.ai_service import AIService

    await _verify_member(household.id, member_id, db)

    prompt = _build_smart_report_prompt(member_id)

    ai_service = AIService(db, household_id=household.id)
    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
        ),
        db,
    )
