"""Family member router."""
import asyncio
import json
import logging
from datetime import date, datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.core.sse import make_sse_stream
from app.services.member_service import MemberService
from app.schemas.family_member import (
    FamilyMemberCreate,
    FamilyMemberUpdate,
    FamilyMemberResponse,
)
from app.models.base import Household, HealthRecord, RecordType, FamilyMember
from app.models.ai import AIInsight
from app.models.provider import Provider, ProviderAssignment
from app.schemas.provider_assignment import ProviderAssignmentResponse
from app.core.cache import cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Family Members"])

_COMPREHENSIVE_INSIGHT_PROMPT = (
    "You are a senior physician writing a formal clinical health assessment report after a thorough "
    "chart review. You MUST reference every condition, diagnosis, provider, and medication found in "
    "the patient data. Do NOT omit any named conditions, diagnoses, doctors, or providers.\n\n"
    "DATA SOURCES — use ALL of these:\n"
    "- Patient profile: self-reported medical history, conditions, allergies, surgeries, medications\n"
    "- Doctor visits: every consultation note, diagnosis, and prescription from each provider\n"
    "- Lab reports: all test results, values, and reference ranges\n"
    "- Prescriptions: all active and past medications with dosages, durations, and timing\n"
    "- Medication summary: the aggregated list of ALL current medications\n"
    "- Lab trends: serial values for key tests with dates\n\n"
    "OUTPUT exactly these 6 sections with these exact headings:\n\n"
    "1. **Health Overview**\n"
    "Open with the patient's age, sex, and primary clinical concern. "
    "List every diagnosed condition with its first-documented date if available. "
    "Name every provider currently involved in their care. "
    "Note relevant demographic risk factors (age-related screening needs, family history indicators). "
    "Summarize the overall health trajectory in 2-3 sentences.\n\n"
    "2. **Active Conditions**\n"
    "For EACH diagnosed condition, assess its current trajectory "
    "(improving / stable / worsening / inadequately controlled) with supporting evidence from "
    "lab values, medication changes, or visit notes. "
    "Pattern: state the condition, cite the latest relevant value or note, compare to prior if available, "
    "and give a clinical status assessment. "
    "Example: 'T2DM diagnosed 2024, currently suboptimally controlled — latest **HbA1c 8.9%** "
    "(target <7% per ADA) on Metformin 500mg BID, deteriorated from 7.2% on [date].'\n"
    "When discussing medications for a condition, include the drug name, dosage, frequency, "
    "and whether the records explicitly link it to that condition.\n\n"
    "3. **Lab Trends**\n"
    "For each lab test with serial results, present: date, value, reference range, "
    "and clinical status (normal/abnormal/critical). State the trajectory with specific values: "
    "'Fasting glucose rose from **110 mg/dL** (09-Jan-2025) to **142 mg/dL** (15-Mar-2025), "
    "crossing from pre-diabetic to diabetic range.' "
    "Highlight every value outside reference range and explain its clinical significance "
    "in the context of the patient's known conditions.\n\n"
    "4. **Risk Assessment**\n"
    "Identify specific risks derived from the COMBINATION of this patient's "
    "conditions, medications, lab values, and demographics. Each risk MUST cite the specific data "
    "driving it. Reference clinical criteria where applicable (ADA, NCEP ATP III, etc.). "
    "Example: 'Elevated cardiovascular risk: patient has T2DM with HbA1c 8.9%, co-existing "
    "hypertension on Met XL 25mg, and total cholesterol 195 mg/dL — meeting metabolic syndrome criteria.'\n\n"
    "5. **Recommendations**\n"
    "Every recommendation must follow: specific finding → clinical implication → "
    "recommended action. Never give generic advice. "
    "Include: overdue screenings, medication adjustments to discuss with their provider, "
    "lifestyle interventions targeting their specific conditions. "
    "Example: 'Given fasting glucose of **142 mg/dL** on Metformin 500mg BID, discuss dose escalation "
    "or addition of a second agent (e.g., SGLT2 inhibitor for cardiorenal benefit) with endocrinologist.'\n\n"
    "6. **Follow-up Actions**\n"
    "List by clinical priority (urgent > important > routine). "
    "For each: the action needed, the reason (citing specific data), and the specific deadline or "
    "next review date if recorded. Flag any overdue follow-ups from the records.\n\n"
    "STYLE RULES:\n"
    "- Write in professional clinical prose paragraphs, NOT bullet-point lists.\n"
    "- Each section should be as long as clinically warranted — prioritize specificity over brevity.\n"
    "- When referencing a medication, include its full name, dosage, and frequency in the same sentence.\n"
    "- When referencing a lab value, include the value, units, reference range, and date.\n"
    "- Bold key values and terms with **double asterisks**.\n"
    "- No preamble, no closing remarks — start directly with section 1.\n\n"
    "ACCURACY RULES (CRITICAL):\n"
    "- NEVER guess what a medication is used for. If the records do not explicitly state "
    "the indication for a drug, write 'indication per records: not specified' rather than guessing.\n"
    "- Common errors to AVOID: assuming Metoprolol/Met XL is for diabetes (it is for BP/heart), "
    "assuming Rivotril/Clonazepam is for anxiety only (check the diagnosis), "
    "confusing Syndopa (Parkinson's) with diabetes medication.\n"
    "- Only state a drug's purpose if the patient's records explicitly link it to a diagnosis, "
    "OR the prescription note specifies the indication.\n"
    "- If unsure about a drug's indication, say so explicitly rather than risk an incorrect statement.\n"
)


@router.get("", response_model=list[FamilyMemberResponse])
async def list_members(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    is_active: bool | None = Query(True),
):
    """List all family members in household."""
    cache_key = f"members:{household.id}:{is_active}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    service = MemberService(db)
    members = await service.list_members(household.id, is_active)
    cache.set(cache_key, members, ttl=120)
    return members


@router.post("", status_code=201, response_model=FamilyMemberResponse)
async def create_member(
    request: FamilyMemberCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Add a new family member with medical history questionnaire."""
    service = MemberService(db)

    member = await service.create_member(
        household_id=household.id,
        first_name=request.first_name,
        last_name=request.last_name,
        date_of_birth=request.date_of_birth,
        gender=request.gender,
        relationship=request.relationship,
        medical_history=request.medical_history,
        allergies=[a.model_dump() for a in request.allergies] if request.allergies else None,
        emergency_contact_name=request.emergency_contact_name,
        emergency_contact_phone=request.emergency_contact_phone,
        height_cm=request.height_cm,
        weight_kg=request.weight_kg,
    )
    cache.invalidate(f"members:{household.id}")
    return member


@router.get("/batch-scores")
async def get_batch_scores(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return dashboard summary scores for ALL active members in one call.

    Eliminates the N+1 pattern of calling /members/{id}/dashboard per member.
    Uses aggregate queries instead of loading full dashboards.
    """
    # Fetch all active members
    members_result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.household_id == household.id,
            FamilyMember.is_active.is_(True),
        )
    )
    members = list(members_result.scalars().all())

    if not members:
        return []

    member_ids = [m.id for m in members]

    # Aggregate: total_records per member
    counts_result = await db.execute(
        select(
            HealthRecord.family_member_id,
            func.count().label("total_records"),
        )
        .where(
            HealthRecord.family_member_id.in_(member_ids),
            HealthRecord.is_deleted.is_(False),
        )
        .group_by(HealthRecord.family_member_id)
    )
    record_counts = {row[0]: row[1] for row in counts_result.all()}

    # Aggregate: latest_record_date per member
    latest_result = await db.execute(
        select(
            HealthRecord.family_member_id,
            func.max(HealthRecord.record_date).label("latest_date"),
        )
        .where(
            HealthRecord.family_member_id.in_(member_ids),
            HealthRecord.is_deleted.is_(False),
        )
        .group_by(HealthRecord.family_member_id)
    )
    latest_dates = {row[0]: row[1] for row in latest_result.all()}

    # Aggregate: active_medications count per member (doctor_visit records with prescriptions)
    med_result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.family_member_id.in_(member_ids),
            HealthRecord.record_type == RecordType.DOCTOR_VISIT,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
    )
    med_records = list(med_result.scalars().all())

    # Count unique active medications per member (dedup by name across providers)
    med_counts: dict = {}
    # Group records by member
    member_records: dict = {}
    for r in med_records:
        if r.family_member_id not in member_records:
            member_records[r.family_member_id] = []
        member_records[r.family_member_id].append(r)

    for mid, recs in member_records.items():
        seen_names: set[str] = set()
        count = 0
        for r in recs:
            if not r.clinical_data:
                continue
            try:
                parsed = json.loads(r.clinical_data)
                if isinstance(parsed, dict) and parsed.get("_type") == "structured":
                    for rx in parsed.get("prescriptions", []):
                        name = (rx.get("medicine") or "").strip()
                        if name:
                            base = name.lower().split()[0]
                            if base not in seen_names:
                                seen_names.add(base)
                                count += 1
            except (json.JSONDecodeError, ValueError):
                continue
        med_counts[mid] = count

    return [
        {
            "member_id": str(m.id),
            "first_name": m.first_name,
            "last_name": m.last_name,
            "total_records": record_counts.get(m.id, 0),
            "latest_record_date": (d.isoformat() if (d := latest_dates.get(m.id)) is not None else None),
            "active_medications_count": med_counts.get(m.id, 0),
        }
        for m in members
    ]


@router.get("/{member_id}", response_model=FamilyMemberResponse)
async def get_member(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get family member details."""
    service = MemberService(db)
    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.put("/{member_id}", response_model=FamilyMemberResponse)
async def update_member(
    member_id: UUID,
    request: FamilyMemberUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update family member profile."""
    service = MemberService(db)

    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    update_data = request.model_dump(exclude_unset=True)

    # Convert structured allergies list to JSON string for storage
    if "allergies" in update_data:
        allergies_list = update_data.pop("allergies")
        if allergies_list is not None:
            update_data["allergies_json"] = json.dumps(allergies_list)
        else:
            update_data["allergies_json"] = None

    member = await service.update_member(member_id, **update_data)
    cache.invalidate(f"members:{household.id}")
    return member


@router.delete("/{member_id}", status_code=204)
async def delete_member(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a family member."""
    service = MemberService(db)

    try:
        await service.soft_delete_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    cache.invalidate(f"members:{household.id}")
    cache.invalidate(f"household_records:{household.id}")


@router.get("/{member_id}/bmi-history")
async def get_bmi_history(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return BMI history from VITALS records for sparkline chart."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

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
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

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

    history = []
    for r in records:
        try:
            data = json.loads(r.clinical_data) if r.clinical_data else {}
            if not isinstance(data, dict):
                continue
            # Direct hba1c_value field (blood_glucose records)
            if "hba1c_value" in data:
                history.append({
                    "date": r.record_date.isoformat(),
                    "hba1c_value": float(data["hba1c_value"]),
                })
                continue
            # Scan lab_results table in doctor_visit records
            for key in ("lab_results", "tests"):
                lab_list = data.get(key)
                if not isinstance(lab_list, list):
                    continue
                for test in lab_list:
                    if not isinstance(test, dict):
                        continue
                    name = (test.get("test_name") or "").lower()
                    if "hba1c" in name or "glycated" in name or "glycosylated" in name or "a1c" in name:
                        result_str = test.get("result", "")
                        # Extract numeric value from result like "8.9 %" or "8.9%"
                        import re
                        match = re.search(r"(\d+\.?\d*)", str(result_str))
                        if match:
                                val = float(match.group(1))
                                if 3.0 <= val <= 15.0:  # valid HbA1c range
                                    history.append({
                                        "date": r.record_date.isoformat(),
                                        "hba1c_value": val,
                                    })
                                    break
                else:
                    continue
                break
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    return history


@router.get("/{member_id}/lab-trends-interpretation")
async def get_lab_trends_interpretation(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get AI-interpreted lab trend analysis for a member."""
    from app.services.ai_service import AIService

    service = MemberService(db)
    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    ai_service = AIService(db)

    # Build a focused lab data summary for the AI (not the full clinical_data blob)
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

    # Parse the response
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
    prompt = _COMPREHENSIVE_INSIGHT_PROMPT
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

    # Fire-and-forget verification using a different AI provider
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
    prompt = _COMPREHENSIVE_INSIGHT_PROMPT

    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
        ),
        db,
    )


_PRE_CONSULT_PROMPT = (
    "You are a clinical assistant preparing a pre-consultation inquiry sheet for a patient's upcoming "
    "doctor visit. Generate 8-12 focused clinical questions that the patient should raise with their "
    "physician.\n\n"
    "Use ALL available patient data: demographics, medical history, diagnosed conditions, all "
    "medications with dosages, lab results with dates and reference ranges, visit notes, vitals, "
    "and any overdue follow-ups."
    "{specialty_section}"
    "{symptoms_section}\n\n"
    "OUTPUT FORMAT — produce EXACTLY this structure:\n\n"
    "### **Pre-Consultation Clinical Inquiry**\n"
    "*(AI-generated questions based on the patient's medical history and reported symptoms "
    "for discussion with the attending physician.)*\n\n"
    "Then list 8-12 items. Each item MUST follow this exact pattern:\n"
    "* **Category (Detail):** Specific clinical question that references concrete patient data.\n\n"
    "CATEGORIES (use the most relevant ones for this patient):\n"
    "- **Medication Review (Drug Names)**: Questions about concurrent use, contraindications, "
    "duplicate therapy, or interactions between the patient's specific medications. "
    "Always name the drugs involved.\n"
    "- **Symptom Assessment (Body Area)**: Questions about the etiology, significance, "
    "or workup for a reported symptom. Always name the body area and reference relevant history.\n"
    "- **Lab Result Interpretation (Test Name)**: Ask what a specific abnormal or borderline "
    "lab value implies given the patient's known conditions. Cite the exact value, date, and reference range.\n"
    "- **Dosage Optimization (Drug Name)**: Ask whether a current dosage is appropriate given "
    "the latest lab values, weight changes, or disease progression.\n"
    "- **Treatment Efficacy (Condition)**: Ask whether a current treatment is achieving its "
    "target based on the most recent data (e.g., HbA1c still above target, BP still elevated).\n"
    "- **Follow-up Planning (Test/Screening)**: Ask when a repeat test, screening, or follow-up "
    "visit is due. Reference the last date performed and recommended interval.\n"
    "- **Preventive Care**: Ask about overdue vaccinations, age-appropriate screenings, "
    "or lifestyle interventions specific to the patient's conditions.\n"
    "- **Referral Need (Specialty)**: Ask whether a specialist referral is warranted for a "
    "specific concern, citing the relevant findings.\n"
    "- **New Concern Investigation**: If the patient reported new symptoms, ask about "
    "differential diagnosis, recommended workup, or urgency assessment.\n"
    "{specialty_focus}\n"
    "RULES:\n"
    "- Every question MUST reference specific data from the patient's records: "
    "exact medication names, lab values with units and dates, diagnosed conditions, visit notes.\n"
    "- Be clinically precise. Use medical terminology appropriate for physician-level discussion.\n"
    "- Prioritize actionable questions that will affect clinical decisions during THIS visit.\n"
    "- Put the most clinically urgent questions first.\n"
    "- No preamble or closing text beyond the header and bullet list.\n"
    "- No filler or generic questions (e.g., 'How is your general health?'). Every item must be data-driven.\n"
    "- If the patient has multiple conditions, ensure questions address EACH condition, not just the primary one.\n"
    "- Include at least one question about medication interactions if the patient takes 3+ medications.\n"
)


async def _get_provider_specialty_context(
    provider_id: UUID | None, household_id: UUID, db: AsyncSession
) -> tuple[str, str]:
    """Look up provider specialty for pre-consultation prompt tailoring.

    Returns (specialty_section, specialty_focus) strings to inject into the prompt.
    """
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
            f"- **{provider.speciality} Assessment**: Add questions specifically relevant "
            f"to a {provider.speciality} consultation."
        )
    return specialty_section, specialty_focus


@router.post("/{member_id}/pre-consultation-note")
async def generate_pre_consultation_note(
    member_id: UUID,
    provider_id: UUID | None = None,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Generate a pre-consultation note based on member's full medical history."""
    from app.services.ai_service import AIService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    # Append overdue follow-up context
    overdue_result = await db.execute(
        select(HealthRecord)
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
        provider_id, household.id, db
    )

    symptoms_section = ""

    prompt_body = _PRE_CONSULT_PROMPT.format(
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

    prompt = f"__preconsult__{member_id}__\n\n{prompt_body}"

    ai_service = AIService(db)
    try:
        insight = await ai_service.generate_insight(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
        )
        await db.commit()

        # Fire-and-forget verification using a different AI provider
        try:
            from app.services.insight_service import spawn_insight_verification_task
            context = await ai_service._build_member_context(member_id, comprehensive=True)
            spawn_insight_verification_task(insight.id, context)
        except Exception:
            logger.debug("Pre-consultation verification skipped")
    except Exception as exc:
        logger.error("Pre-consultation note generation failed: %s", exc)
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


@router.get("/{member_id}/pre-consultation-note/latest")
async def get_latest_pre_consultation_note(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest persisted pre-consultation note, or null."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.prompt.like(f"__preconsult__{member_id}__%"),
            AIInsight.health_record_id.is_(None),
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        return {"note": None}

    return {
        "note": {
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


@router.post("/{member_id}/pre-consultation-note/stream")
async def generate_pre_consultation_note_stream(
    member_id: UUID,
    symptoms: str | None = Query(None),
    provider_id: UUID | None = Query(None),
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Stream pre-consultation note generation with real-time progress (SSE)."""
    from app.services.ai_service import AIService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    # Append overdue follow-up context
    overdue_result = await db.execute(
        select(HealthRecord)
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
        provider_id, household.id, db
    )

    symptoms_section = ""
    if symptoms and symptoms.strip():
        symptoms_section = f"\n\nPATIENT-REPORTED SYMPTOMS:\n{symptoms.strip()}"

    prompt_body = _PRE_CONSULT_PROMPT.format(
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

    prompt = f"__preconsult__{member_id}__\n\n{prompt_body}"

    ai_service = AIService(db)
    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            member_id=member_id,
            comprehensive=True,
        ),
        db,
    )


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

    # Run independent queries in parallel
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
        .where(ProviderAssignment.family_member_id == member_id)
        .order_by(ProviderAssignment.created_at.desc())
    )
    active_medications, recent_records_result, assignments_result = await asyncio.gather(
        active_medications_coro, recent_records_coro, assignments_coro
    )

    # Count conditions from medical_history_summary
    conditions_count = 0
    if member.medical_history_summary:
        for part in member.medical_history_summary.split("; "):
            if part.startswith("Conditions:"):
                conditions_count = len([x.strip() for x in part.replace("Conditions:", "").split(",") if x.strip()])
                break

    # Compute age
    today = date.today()
    age = today.year - member.date_of_birth.year - (
        (today.month, today.day) < (member.date_of_birth.month, member.date_of_birth.day)
    )

    recent_records = list(recent_records_result.scalars().all())

    # Build provider assignment responses
    assignments = assignments_result.scalars().all()
    assignment_responses = []
    for a in assignments:
        prov = await db.get(Provider, a.provider_id)
        assignment_responses.append(
            ProviderAssignmentResponse(
                id=a.id,
                provider_id=a.provider_id,
                provider_name=prov.name if prov else "Unknown",
                family_member_id=a.family_member_id,
                family_member_name=f"{member.first_name} {member.last_name}",
                uhid=a.uhid,
                created_at=a.created_at,
            ).model_dump()
        )

    health_score, score_breakdown = _compute_health_score(
        member, conditions_count, active_medications, recent_records, age
    )

    result = {
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

    return result


def _compute_health_score(
    member: "FamilyMember",  # noqa: F821
    conditions_count: int,
    active_medications: list,
    recent_records: list,
    age: int,
) -> tuple[int, dict]:
    """Compute enhanced health score with category breakdown.

    Returns (total_score, breakdown_dict) where breakdown contains
    per-category scores with labels explaining the assessment.
    """
    breakdown: dict[str, dict] = {}
    total = 0

    # 1. BMI component (0-20)
    bmi_score = 10  # default: no data
    bmi_label = "No BMI data available"
    if member.height_cm and member.weight_kg and member.height_cm > 0:
        hm = member.height_cm / 100
        bmi = round(member.weight_kg / (hm * hm), 1)
        if 18.5 <= bmi < 25:
            bmi_score = 20
            bmi_label = f"BMI {bmi} — normal range"
        elif 25 <= bmi < 30:
            bmi_score = 14
            bmi_label = f"BMI {bmi} — overweight"
        elif 30 <= bmi < 35:
            bmi_score = 8
            bmi_label = f"BMI {bmi} — obese class I"
        else:
            bmi_score = 5
            bmi_label = f"BMI {bmi} — obese class II+"
    total += bmi_score
    breakdown["bmi"] = {"score": bmi_score, "max": 20, "label": bmi_label}

    # 2. Conditions management (0-20) — reward having recent checkups
    cond_score = 20
    cond_label = "No known chronic conditions"
    if conditions_count > 0:
        # Check if there's been a doctor visit in the last 6 months
        six_months_ago = date.today().replace(month=date.today().month - 6) if date.today().month > 6 else date.today().replace(year=date.today().year - 1, month=date.today().month + 6)
        has_recent_visit = any(
            r.record_type == RecordType.DOCTOR_VISIT and r.record_date >= six_months_ago
            for r in recent_records
        )
        if has_recent_visit:
            cond_score = 16
            cond_label = f"{conditions_count} condition(s), recent checkup within 6 months"
        else:
            cond_score = 8
            cond_label = f"{conditions_count} condition(s), no recent checkup"
    total += cond_score
    breakdown["conditions_management"] = {"score": cond_score, "max": 20, "label": cond_label}

    # 3. Lab compliance (0-20) — are recent labs within reference range?
    lab_score = 10  # neutral: no lab data
    lab_label = "No recent lab data"
    lab_records = [r for r in recent_records if r.record_type in (RecordType.LAB_REPORT, RecordType.BLOOD_GLUCOSE)]
    if lab_records:
        normal_count = 0
        abnormal_count = 0
        for r in lab_records[:5]:  # check last 5 lab records
            try:
                parsed = json.loads(r.clinical_data or "")
                for key in ("tests", "lab_results"):
                    for t in parsed.get(key) or []:
                        if isinstance(t, dict):
                            note = (t.get("note") or "").lower()
                            if "critical" in note or "high" in note or "elevated" in note or "low" in note:
                                abnormal_count += 1
                            elif "normal" in note or "well" in note:
                                normal_count += 1
            except (json.JSONDecodeError, ValueError):
                continue
        if abnormal_count == 0 and normal_count > 0:
            lab_score = 20
            lab_label = "All recent lab results normal"
        elif normal_count >= abnormal_count:
            lab_score = 14
            lab_label = f"Mostly normal ({normal_count} normal, {abnormal_count} flagged)"
        elif abnormal_count > 0:
            lab_score = 6
            lab_label = f"{abnormal_count} abnormal result(s) flagged"
    total += lab_score
    breakdown["lab_compliance"] = {"score": lab_score, "max": 20, "label": lab_label}

    # 4. Medication tracking (0-15) — reward tracking, not penalize count
    med_count = len(active_medications)
    if med_count == 0:
        med_score = 15
        med_label = "No active medications"
    else:
        # Having medications tracked is good management
        med_score = 12
        med_label = f"{med_count} medication(s) actively tracked"
        # Deduct if no follow-up visit for medications
        has_followup = any(r.next_review_date for r in recent_records[:5])
        if has_followup:
            med_score = 15
            med_label = f"{med_count} medication(s) tracked with follow-up scheduled"
    total += med_score
    breakdown["medication_tracking"] = {"score": med_score, "max": 15, "label": med_label}

    # 5. Profile completeness (0-15)
    profile_score = 0
    profile_items = []
    if member.blood_group:
        profile_score += 5
        profile_items.append("blood group")
    if member.emergency_contact_name or member.emergency_contact_phone:
        profile_score += 5
        profile_items.append("emergency contact")
    if member.medical_history_summary:
        profile_score += 5
        profile_items.append("medical history")
    if member.allergies_json:
        try:
            allergies = json.loads(member.allergies_json)
            if isinstance(allergies, list) and len(allergies) > 0:
                profile_items.append("allergies")
        except (ValueError, json.JSONDecodeError):
            pass
    missing = 15 - profile_score
    profile_label = f"Complete ({', '.join(profile_items)})" if profile_score >= 15 else f"Missing {missing} pts of data"
    total += profile_score
    breakdown["profile_completeness"] = {"score": profile_score, "max": 15, "label": profile_label}

    # 6. Record recency (0-10) — reward keeping records up to date
    recency_score = 0
    if recent_records:
        latest = recent_records[0].record_date
        days_since = (date.today() - latest).days
        if days_since <= 30:
            recency_score = 10
            recency_label = f"Last record {days_since} days ago"
        elif days_since <= 90:
            recency_score = 7
            recency_label = f"Last record {days_since} days ago"
        elif days_since <= 180:
            recency_score = 4
            recency_label = f"Last record {days_since // 30} months ago"
        else:
            recency_score = 1
            recency_label = f"Last record over {days_since // 30} months ago"
    else:
        recency_score = 0
        recency_label = "No records yet"
    total += recency_score
    breakdown["record_recency"] = {"score": recency_score, "max": 10, "label": recency_label}

    return min(100, total), breakdown


@router.get("/{member_id}/preventive-recommendations")
async def get_preventive_recommendations(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get age- and condition-based preventive care recommendations."""
    from app.services.preventive_care_service import PreventiveCareService

    service = MemberService(db)
    try:
        member = await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    care_service = PreventiveCareService(db)
    recommendations = await care_service.generate_recommendations(member)
    return {"recommendations": recommendations}


class PreventiveReminderRequest(BaseModel):
    """Validated request body for preventive-reminders."""
    title: str = Field("Preventive care reminder", max_length=200)
    description: str = Field("", max_length=1000)
    due_interval_months: int = Field(12, ge=1, le=120)


@router.post("/{member_id}/preventive-reminders")
async def create_preventive_reminder(
    member_id: UUID,
    body: PreventiveReminderRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Convert a preventive care recommendation into a reminder."""
    from app.services.reminder_service import ReminderService
    from app.models.base import ReminderType, ScheduleType
    from datetime import datetime, timedelta

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    title = body.title
    description = body.description
    months = body.due_interval_months
    due_date = datetime.now() + timedelta(days=months * 30)

    reminder_svc = ReminderService(db)
    reminder = await reminder_svc.create_reminder(
        household_id=household.id,
        reminder_type=ReminderType.CHECK_UP,
        title=title,
        description=description,
        schedule_type=ScheduleType.ONCE,
        start_datetime=due_date,
        member_id=member_id,
    )
    return {"id": str(reminder.id), "title": title, "due_date": due_date.isoformat()}


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

    # Find latest comprehensive member insight (no record/conversation binding)
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

    # None found — auto-generate
    from app.services.ai_service import AIService
    ai_service = AIService(db)
    prompt = _COMPREHENSIVE_INSIGHT_PROMPT
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

    # Check for cached drug interactions (<24h old)
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

    # Generate fresh
    from app.services.ai_service import AIService
    ai_service = AIService(db)
    try:
        interactions = await ai_service.check_drug_interactions(medications)
        # Persist
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


# --- Medication CRUD ---

class MedicationInput(BaseModel):
    """Single prescription row."""
    type: str = Field("", description="Tab/Cap/Inj/etc")
    medicine: str = Field(..., min_length=1, description="Medicine name + strength")
    dosage: str = Field("", description="e.g. 1-1-1")
    duration: str = Field("", description="e.g. 30 days")
    timing: str = Field("", description="before_food/after_food/etc")
    note: str = Field("", description="Optional note")


class MedicationUpdate(BaseModel):
    """Update an existing prescription by index in its record."""
    record_id: UUID = Field(..., description="Source health record ID")
    prescription_index: int = Field(..., description="Index in prescriptions array")
    data: MedicationInput = Field(...)


class MedicationDelete(BaseModel):
    """Delete a prescription by record + index."""
    record_id: UUID = Field(..., description="Source health record ID")
    prescription_index: int = Field(..., description="Index in prescriptions array")


class MedicationBulkDelete(BaseModel):
    """Delete multiple prescriptions across records."""
    items: list[MedicationDelete] = Field(..., description="List of prescriptions to delete")


class MedicationDiffRequest(BaseModel):
    """Request body for medication diff computation."""
    prescriptions: list[dict] = Field(..., description="New prescriptions to compare")
    record_id: str | None = Field(None, description="Source record ID for context")


class MedicationApplyRequest(BaseModel):
    """Request body for applying medication sync changes."""
    apply_added: list[str] = Field(default_factory=list, description="Medicine names to add")
    apply_updated: list[str] = Field(default_factory=list, description="Medicine names to update")
    apply_removed: list[str] = Field(default_factory=list, description="Medicine names to remove")


def _rebuild_clinical_data(parsed: dict, prescriptions: list[dict]) -> str:
    """Rebuild clinical_data JSON with updated prescriptions."""
    parsed["prescriptions"] = prescriptions
    parsed["_type"] = "structured"
    return json.dumps(parsed)


async def _find_prescription_record(db, member_id: UUID, record_id: UUID):
    """Load a health record and verify it belongs to the member."""
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id == record_id,
            HealthRecord.family_member_id == member_id,
            HealthRecord.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


@router.post("/{member_id}/medications", status_code=201)
async def add_medication(
    member_id: UUID,
    body: MedicationInput,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Add a single medication as a new doctor_visit record."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    rx = body.model_dump()
    clinical_data = json.dumps({
        "_type": "structured",
        "_version": 1,
        "_recordType": "doctor_visit",
        "prescriptions": [rx],
    })

    record = HealthRecord(
        family_member_id=member_id,
        record_type=RecordType.DOCTOR_VISIT,
        record_date=date.today(),
        clinical_data=clinical_data,
    )
    db.add(record)
    await db.flush()

    # Remove older prescriptions for the same medicine
    from app.services.medication_service import MedicationService
    med_svc = MedicationService(db)
    med_name = rx.get("medicine", "").strip()
    if med_name:
        await med_svc.remove_outdated_prescriptions(member_id, [med_name])

    await db.commit()
    cache.invalidate(f"dashboard:{member_id}")
    return {
        "id": str(record.id),
        "prescription": rx,
        "record_id": str(record.id),
        "prescription_index": 0,
    }


@router.put("/{member_id}/medications")
async def update_medication(
    member_id: UUID,
    body: MedicationUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update a specific prescription within a health record."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    record = await _find_prescription_record(db, member_id, body.record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    try:
        parsed = json.loads(record.clinical_data)
        if not isinstance(parsed, dict):
             raise HTTPException(status_code=400, detail="Cannot edit unstructured record")
             
        prescriptions = parsed.get("prescriptions", [])
        if not isinstance(prescriptions, list):
             raise HTTPException(status_code=400, detail="Record has no prescriptions list")

        if body.prescription_index < 0 or body.prescription_index >= len(prescriptions):
            raise HTTPException(status_code=400, detail="Invalid prescription index")
        
        prescriptions[body.prescription_index] = body.data.model_dump()
        record.clinical_data = _rebuild_clinical_data(parsed, prescriptions)
        await db.flush()
    except (json.JSONDecodeError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Cannot edit unstructured record")

    cache.invalidate(f"dashboard:{member_id}")
    return {"updated": True}


@router.delete("/{member_id}/medications")
async def delete_medication(
    member_id: UUID,
    body: MedicationDelete,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific prescription from a health record.
    If it was the only prescription, soft-delete the entire record."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    record = await _find_prescription_record(db, member_id, body.record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    try:
        parsed = json.loads(record.clinical_data)
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Cannot edit unstructured record")
            
        prescriptions = parsed.get("prescriptions", [])
        if not isinstance(prescriptions, list):
             raise HTTPException(status_code=400, detail="Record has no prescriptions list")
             
        if body.prescription_index < 0 or body.prescription_index >= len(prescriptions):
            raise HTTPException(status_code=400, detail="Invalid prescription index")
        
        prescriptions.pop(body.prescription_index)

        # Always update clinical_data
        record.clinical_data = _rebuild_clinical_data(parsed, prescriptions)
        
        if len(prescriptions) == 0:
            # No prescriptions left — soft-delete the record
            record.is_deleted = True
            
        await db.flush()
    except (json.JSONDecodeError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Cannot edit unstructured record")

    cache.invalidate(f"dashboard:{member_id}")
    return {"deleted": True}


@router.post("/{member_id}/medications/bulk-delete")
async def bulk_delete_medications(
    member_id: UUID,
    body: MedicationBulkDelete,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple prescriptions across records in one request.

    Groups items by record, sorts indices descending within each group,
    and pops from highest index first to keep earlier indices valid.
    """
    logger.info("bulk-delete: received %d items for member %s", len(body.items), member_id)
    for item in body.items:
        logger.info("bulk-delete: item record_id=%s prescription_index=%d", item.record_id, item.prescription_index)

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    # Group by record_id, sort unique indices descending
    by_record: dict[str, set[int]] = {}
    for item in body.items:
        key = str(item.record_id)
        by_record.setdefault(key, set()).add(item.prescription_index)

    deleted = 0
    for record_id_str, indices_set in by_record.items():
        indices = sorted(list(indices_set), reverse=True)
        try:
            record = await _find_prescription_record(db, member_id, UUID(record_id_str))
        except ValueError:
            logger.warning("bulk-delete: invalid UUID %s", record_id_str)
            continue

        if not record:
            logger.warning("bulk-delete: record %s not found for member %s", record_id_str, member_id)
            continue
        if not record.clinical_data:
            logger.warning("bulk-delete: record %s has no clinical_data", record_id_str)
            continue

        try:
            parsed = json.loads(record.clinical_data)
            if not isinstance(parsed, dict):
                logger.warning("bulk-delete: record %s clinical_data is not a dict", record_id_str)
                continue

            prescriptions = parsed.get("prescriptions", [])
            if not isinstance(prescriptions, list) or not prescriptions:
                logger.warning(
                    "bulk-delete: record %s has no prescriptions list (clinical_data keys: %s)",
                    record_id_str, list(parsed.keys()),
                )
                continue

            for idx in indices:
                if 0 <= idx < len(prescriptions):
                    prescriptions.pop(idx)
                    deleted += 1
                else:
                    logger.warning(
                        "bulk-delete: index %d out of range [0, %d) for record %s",
                        idx, len(prescriptions), record_id_str,
                    )

            # Always update clinical_data to reflect remaining items
            record.clinical_data = _rebuild_clinical_data(parsed, prescriptions)
            
            if len(prescriptions) == 0:
                record.is_deleted = True
                
            await db.flush()
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            logger.exception("bulk-delete: failed to process record %s", record_id_str)
            continue

    cache.invalidate(f"dashboard:{member_id}")
    return {"deleted": deleted}


@router.post("/{member_id}/medications/diff")
async def compute_medication_diff(
    member_id: UUID,
    body: MedicationDiffRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Compute the diff between new prescriptions and current active medications.

    Returns added, updated, removed, and unchanged lists without applying any changes.
    """
    from app.services.medication_service import MedicationService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    med_svc = MedicationService(db)
    diff = await med_svc.compute_medication_diff(member_id, body.prescriptions)
    return diff


@router.post("/{member_id}/medications/apply-sync")
async def apply_medication_sync(
    member_id: UUID,
    body: MedicationApplyRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Apply confirmed medication sync changes.

    Accepts lists of medicine names to add, update, and remove.
    """
    from app.services.medication_service import MedicationService

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    med_svc = MedicationService(db)
    result = await med_svc.apply_medication_changes(
        member_id,
        apply_added=body.apply_added,
        apply_updated=body.apply_updated,
        apply_removed=body.apply_removed,
    )
    await db.commit()

    cache.invalidate(f"dashboard:{member_id}")
    return result
