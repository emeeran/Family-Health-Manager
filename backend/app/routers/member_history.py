"""Member health history and trends router — BMI, HbA1c, lab trends, dashboard."""
import asyncio
import json
import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household, HealthRecord, RecordType
from app.models.provider import ProviderAssignment
from app.schemas.family_member import FamilyMemberResponse
from app.schemas.provider_assignment import ProviderAssignmentResponse
from app.services.health_score_service import compute_health_score, get_conditions_count, extract_hba1c_history
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Member History"])


async def _verify_member(household_id, member_id: UUID, db: AsyncSession):
    service = MemberService(db)
    try:
        return await service.get_member(household_id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")


@router.get("/{member_id}/bmi-history")
async def get_bmi_history(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return BMI history from VITALS records for sparkline chart."""
    await _verify_member(household.id, member_id, db)

    result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.record_type == RecordType.VITALS,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.asc())
    )
    records = result.scalars().all()

    history = []
    for r in records:
        try:
            data = json.loads(r.clinical_data) if r.clinical_data else {}
            if isinstance(data, dict) and "bmi" in data:
                history.append({
                    "date": r.record_date.isoformat(),
                    "bmi": data["bmi"],
                    "height_cm": data.get("height_cm"),
                    "weight_kg": data.get("weight_kg"),
                })
        except (json.JSONDecodeError, ValueError):
            continue

    return history


@router.get("/{member_id}/hba1c-history")
async def get_hba1c_history(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return HbA1c history from blood_glucose and doctor_visit records."""
    await _verify_member(household.id, member_id, db)

    result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.record_type.in_([RecordType.BLOOD_GLUCOSE, RecordType.DOCTOR_VISIT, RecordType.LAB_REPORT]),
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.asc())
    )
    records = result.scalars().all()

    return extract_hba1c_history(list(records))


@router.get("/{member_id}/lab-trends-interpretation")
async def get_lab_trends_interpretation(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get AI-interpreted lab trend analysis for a member."""
    from app.services.ai_service import AIService

    member = await _verify_member(household.id, member_id, db)
    ai_service = AIService(db)

    result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.record_type.in_([RecordType.LAB_REPORT, RecordType.BLOOD_GLUCOSE]),
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
        .limit(20)
    )
    records = result.scalars().all()

    lab_summary_lines = []
    for r in records:
        if not r.clinical_data:
            continue
        try:
            parsed = json.loads(r.clinical_data)
            if not isinstance(parsed, dict):
                continue
            for key in ("tests", "lab_results"):
                for t in parsed.get(key) or []:
                    if not isinstance(t, dict):
                        continue
                    name = t.get("test_name", "")
                    val = t.get("result", "")
                    ref = t.get("ref_value", "")
                    note = t.get("note", "")
                    lab_summary_lines.append(f"{r.record_date} | {name}: {val} (ref: {ref}) {note}")
        except (json.JSONDecodeError, ValueError):
            continue

    if not lab_summary_lines:
        return {"trends": [], "interpretation": "No lab data available for trend analysis."}

    prompt = (
        f"Patient: {member.first_name} {member.last_name}\n\n"
        f"Lab results over time (newest first):\n"
        + "\n".join(lab_summary_lines[:30])
        + "\n\nFor each unique test, provide a JSON object with:\n"
        '- "test_name": the test name\n'
        '- "direction": "improving", "worsening", or "stable"\n'
        '- "latest_status": "normal", "elevated", "low", or "critical"\n'
        '- "interpretation": one sentence clinical comment\n\n'
        'Return ONLY a JSON array. No markdown, no code fences.'
    )

    try:
        response, provider = await ai_service._call_ai(prompt, "")
    except Exception as exc:
        logger.error("Lab trend interpretation failed: %s", exc)
        return {"trends": [], "interpretation": "AI service unavailable."}

    import re
    cleaned = re.sub(r"```json\s*", "", response or "")
    cleaned = re.sub(r"```\s*", "", cleaned).strip()

    trends = []
    try:
        start = cleaned.find("[")
        if start != -1:
            depth = 0
            for i in range(start, len(cleaned)):
                if cleaned[i] == "[":
                    depth += 1
                elif cleaned[i] == "]":
                    depth -= 1
                    if depth == 0:
                        trends = json.loads(cleaned[start : i + 1])
                        break
    except (json.JSONDecodeError, ValueError):
        pass

    return {"trends": trends, "provider": provider}


@router.get("/{member_id}/dashboard")
async def get_member_dashboard(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get member dashboard with brief medical history, active medications, and health score breakdown."""
    service = MemberService(db)

    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    active_medications_coro = service.get_active_medications(member_id)
    recent_records_coro = db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
        .limit(20)
    )
    assignments_coro = db.execute(
        select(ProviderAssignment)
        .options(joinedload(ProviderAssignment.provider))
        .where(ProviderAssignment.family_member_id == member_id)
        .order_by(ProviderAssignment.created_at.desc())
    )
    active_medications, recent_records_result, assignments_result = await asyncio.gather(
        active_medications_coro, recent_records_coro, assignments_coro
    )

    conditions_count = get_conditions_count(member.medical_history_summary)

    today = date.today()
    age = today.year - member.date_of_birth.year - (
        (today.month, today.day) < (member.date_of_birth.month, member.date_of_birth.day)
    )

    recent_records = list(recent_records_result.scalars().all())

    assignments = assignments_result.scalars().unique().all()
    assignment_responses = []
    for a in assignments:
        assignment_responses.append(
            ProviderAssignmentResponse(
                id=a.id,
                provider_id=a.provider_id,
                provider_name=a.provider.name if a.provider else "Unknown",
                family_member_id=a.family_member_id,
                family_member_name=f"{member.first_name} {member.last_name}",
                uhid=a.uhid,
                created_at=a.created_at,
            ).model_dump()
        )

    health_score, score_breakdown = compute_health_score(
        member, conditions_count, active_medications, recent_records, age
    )

    return {
        "member": FamilyMemberResponse.model_validate(member),
        "brief_medical_history": member.medical_history_summary,
        "active_medications": active_medications,
        "active_conditions_count": conditions_count,
        "active_medications_count": len(active_medications),
        "age": age,
        "health_score": health_score,
        "score_breakdown": score_breakdown,
        "provider_assignments": assignment_responses,
    }
