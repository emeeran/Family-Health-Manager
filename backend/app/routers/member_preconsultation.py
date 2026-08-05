"""Pre-consultation notes router — generate and retrieve doctor visit discussion points."""

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_household_from_token, require_member_in_household
from app.core.sse import make_sse_stream
from app.models.ai import AIInsight
from app.models.base import FamilyMember, Household, HealthRecord
from app.models.provider import Provider
from app.prompts.insight_prompts import PRE_CONSULT_PROMPT
from app.schemas.insight_serializers import serialize_preconsultation_payload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Pre-consultation"])


async def _get_provider_specialty_context(
    provider_id: UUID | None, household_id: UUID, db: AsyncSession
) -> tuple[str, str]:
    """Look up provider specialty for pre-consultation prompt tailoring."""
    if not provider_id:
        return "", ""
    provider_result = await db.execute(
        select(Provider).where(
            Provider.id == provider_id,
            Provider.household_id == household_id,
        )
    )
    provider = provider_result.scalar_one_or_none()
    if not provider:
        return "", ""
    specialty_section = f"\n\nCONSULTATION CONTEXT:\n- Doctor: {provider.name}\n"
    specialty_focus = ""
    if provider.speciality:
        specialty_section += f"- Specialty: {provider.speciality}\n"
        specialty_focus = (
            f"\nSPECIALTY FOCUS — CRITICAL:\n"
            f"This consultation is with a {provider.speciality} specialist. "
            f"ALL questions in section Q MUST be strictly within the {provider.speciality} scope of practice. "
            f"Generate questions that only a {provider.speciality} specialist would answer — "
            f"about disease progression, treatment response, medication optimization within their domain, "
            f"specialist-level investigations, and procedure-related concerns. "
            f"Only reference conditions, labs, or medications from other specialties if they directly "
            f"impact the {provider.speciality} treatment plan "
            f"(e.g., drug interactions, comorbidity complications). "
            f"Do NOT include general practice questions — this patient needs {provider.speciality}-specific, "
            f"clinically sharp questions that probe deeper than a GP would go.\n"
        )
    else:
        specialty_focus = (
            "\nThis is a general consultation. Cover all active health concerns broadly.\n"
        )
    return specialty_section, specialty_focus


async def _build_preconsult_prompt(
    member_id: UUID,
    provider_id: UUID | None,
    symptoms: str | None,
    household_id: UUID,
    db: AsyncSession,
) -> str:
    """Build the full pre-consultation prompt with overdue context and specialty tailoring."""
    overdue_result = await db.execute(
        select(HealthRecord)
        .options(selectinload(HealthRecord.provider))
        .where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.next_review_date < date.today(),
            HealthRecord.is_deleted.is_(False),
            HealthRecord.next_review_date.isnot(None),
        )
        .order_by(HealthRecord.next_review_date.asc())
    )
    overdue_records = overdue_result.scalars().all()

    specialty_section, specialty_focus = await _get_provider_specialty_context(
        provider_id, household_id, db
    )

    symptoms_section = ""
    if symptoms and symptoms.strip():
        symptoms_section = f"\n\nPATIENT-REPORTED SYMPTOMS:\n{symptoms.strip()}"

    prompt_body = PRE_CONSULT_PROMPT.format(
        symptoms_section=symptoms_section,
        specialty_section=specialty_section,
        specialty_focus=specialty_focus,
    )
    if overdue_records:
        overdue_ctx = "\n\nOVERDUE FOLLOW-UPS:\n"
        for r in overdue_records:
            overdue_ctx += f"- [{r.next_review_date}] {r.record_type.value}"
            if r.diagnosis:
                overdue_ctx += f" — {r.diagnosis}"
            if r.provider_name:
                overdue_ctx += f" (Provider: {r.provider_name})"
            overdue_ctx += "\n"
        prompt_body = overdue_ctx + "\n" + prompt_body

    return f"__preconsult__{member_id}__\n\n{prompt_body}"


@router.post("/{member_id}/pre-consultation-note")
async def generate_pre_consultation_note(
    member_id: UUID,
    provider_id: UUID | None = None,
    household: Household = Depends(get_household_from_token),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Generate a pre-consultation note based on member's full medical history."""
    from app.services.ai_service import AIService

    prompt = await _build_preconsult_prompt(member_id, provider_id, None, household.id, db)

    ai_service = AIService(db, household_id=household.id).set_cloud_consent(member.cloud_ai_consent)
    try:
        insight = await ai_service.generate_insight(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
        )
        await db.commit()

        try:
            from app.services.insight_service import verify_insight_inline

            context = await ai_service._build_member_context(member_id, comprehensive=True)
            await verify_insight_inline(db, ai_service, insight, context, member_id)
        except Exception:
            logger.info("Pre-consultation verification skipped")
    except Exception as exc:
        logger.error("Pre-consultation note generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="AI service unavailable. Please try again.")

    return serialize_preconsultation_payload(insight)


@router.get("/{member_id}/pre-consultation-note/latest")
async def get_latest_pre_consultation_note(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest persisted pre-consultation note, or null."""
    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.prompt_key == f"__preconsult__{member_id}__",
            AIInsight.health_record_id.is_(None),
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        return {"note": None}

    return {"note": serialize_preconsultation_payload(insight)}


@router.post("/{member_id}/pre-consultation-note/stream")
async def generate_pre_consultation_note_stream(
    member_id: UUID,
    symptoms: str | None = Query(None),
    provider_id: UUID | None = Query(None),
    household: Household = Depends(get_household_from_token),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Stream pre-consultation note generation with real-time progress (SSE)."""
    from app.services.ai_service import AIService

    try:
        prompt = await _build_preconsult_prompt(member_id, provider_id, symptoms, household.id, db)
    except Exception as exc:
        logger.error("Pre-consultation setup failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Pre-consultation setup failed. Please try again."
        )

    ai_service = AIService(db, household_id=household.id).set_cloud_consent(member.cloud_ai_consent)
    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
        ),
        db,
        request,
    )
