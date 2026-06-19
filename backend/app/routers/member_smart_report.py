"""Smart Report router — generate and retrieve comprehensive health insight per member."""
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
from app.prompts.insight_prompts import SMART_REPORT_PROMPT
from app.schemas.insight_serializers import (
    parse_smart_report_response,
    serialize_smart_report_payload,
)
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


def _smart_postprocess(full_response: str, insight: AIInsight) -> dict:
    """Enrich the streamed ``complete`` frame with the parsed Smart Report.

    Lets the card hand the viewer a first-class structured object the instant
    streaming finishes — no second round-trip, no client-side JSON parsing.
    """
    report, _raw = parse_smart_report_response(full_response)
    return {
        "id": str(insight.id),
        "generated_at": insight.generated_at.isoformat(),
        "report": report.model_dump(mode="json") if report else None,
        "raw_response": insight.response,
    }


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

    # Fire-and-forget cross-verification, matching the streamed/insights path.
    try:
        from app.services.insight_service import spawn_insight_verification_task

        context = await ai_service._build_member_context(member_id, comprehensive=True)
        spawn_insight_verification_task(insight.id, context)
    except Exception:
        logger.debug("Smart Report verification skipped")

    return serialize_smart_report_payload(insight)


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

    return {"report": serialize_smart_report_payload(insight)}


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
            postprocess=_smart_postprocess,
        ),
        db,
    )
