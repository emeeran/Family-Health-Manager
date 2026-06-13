"""Smart entry router — NL parsing for quick record creation."""
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household, FamilyMember, RecordType
from app.services.ai_service import AIService

router = APIRouter(prefix="/smart-entry", tags=["Smart Entry"])
logger = logging.getLogger(__name__)


def _scalar(val) -> str | None:
    """Coerce an AI-parsed scalar (may be int/float/str) to a trimmed string, or None."""
    if val is None:
        return None
    s = str(val).strip()
    return s or None


class NLParseRequest(BaseModel):
    text: str = Field(..., min_length=2, max_length=2000)


class NLFieldPreview(BaseModel):
    label: str
    value: str


class NLMemberMatch(BaseModel):
    id: UUID
    name: str
    matched_by: str  # "name" | "relationship" | "default"


class NLParseResponse(BaseModel):
    member: NLMemberMatch | None = None
    record_type: RecordType | None = None
    record_date: str | None = None
    record_time: str | None = None
    diagnosis: str | None = None
    chief_complaint: str | None = None
    existing_conditions: str | None = None
    investigations: str | None = None
    provider_name: str | None = None
    prescription_text: str | None = None
    prescriptions: list[dict] | None = None
    lab_tests: list[dict] | None = None
    clinical_notes: str | None = None
    next_review_date: str | None = None
    # Structured type-specific fields (persisted into clinical_data by the client)
    glucose_value: str | None = None
    meal_timing: str | None = None
    hba1c_value: str | None = None
    weight: str | None = None
    blood_pressure: str | None = None
    heart_rate: str | None = None
    temperature: str | None = None
    confidence: str = "medium"  # high | medium | low
    preview_fields: list[NLFieldPreview] = []


@router.post("/parse-nl", response_model=NLParseResponse)
async def parse_natural_language(
    request: NLParseRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Parse natural language text into structured health record fields."""
    # Fetch household members for name matching
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.household_id == household.id,
            FamilyMember.is_active.is_(True),
        )
    )
    members = list(result.scalars().all())

    if not members:
        raise HTTPException(status_code=400, detail="No family members found. Add a member first.")

    # Build member context for AI
    member_list = "\n".join(
        f"- ID: {m.id}, Name: {m.first_name} {m.last_name}, "
        f"Relationship: {m.relationship_type.value}, DOB: {m.date_of_birth}"
        for m in members
    )

    ai_service = AIService(db, household_id=household.id)
    parsed = await ai_service.parse_natural_language(request.text, member_list)

    # Fuzzy match member from AI response
    member_match = None
    member_name_raw = parsed.get("member_name", "")
    if member_name_raw:
        member_name_lower = member_name_raw.lower().strip()
        # Exact match first
        for m in members:
            full = f"{m.first_name} {m.last_name}".lower()
            if full == member_name_lower or m.first_name.lower() == member_name_lower:
                member_match = NLMemberMatch(
                    id=m.id,
                    name=f"{m.first_name} {m.last_name}",
                    matched_by="name",
                )
                break
        # Relationship match
        if not member_match:
            rel_map = {
                "dad": "father", "mom": "mother", "papa": "father", "mama": "mother",
                "appa": "father", "amma": "mother", "father": "father", "mother": "mother",
                "son": "son", "daughter": "daughter", "wife": "spouse", "husband": "spouse",
                "spouse": "spouse", "brother": "brother", "sister": "sister",
                "grandfather": "grandfather", "grandmother": "grandmother",
            }
            rel_key = rel_map.get(member_name_lower)
            if rel_key:
                for m in members:
                    if m.relationship_type.value == rel_key:
                        member_match = NLMemberMatch(
                            id=m.id,
                            name=f"{m.first_name} {m.last_name}",
                            matched_by="relationship",
                        )
                        break
        # Partial name match
        if not member_match:
            for m in members:
                full = f"{m.first_name} {m.last_name}".lower()
                if member_name_lower in full or full.startswith(member_name_lower):
                    member_match = NLMemberMatch(
                        id=m.id,
                        name=f"{m.first_name} {m.last_name}",
                        matched_by="name",
                    )
                    break

    # Default to first member if AI didn't identify one
    if not member_match and members:
        member_match = NLMemberMatch(
            id=members[0].id,
            name=f"{members[0].first_name} {members[0].last_name}",
            matched_by="default",
        )

    # Build preview fields
    preview_fields: list[NLFieldPreview] = []
    record_type_raw = parsed.get("record_type")
    record_type = None
    if record_type_raw:
        try:
            record_type = RecordType(record_type_raw)
            type_labels = {
                "doctor_visit": "Doctor Visit",
                "lab_report": "Lab Report",
                "rx_eyeglass": "Eyeglass Rx",
                "blood_glucose": "Blood Glucose",
                "hba1c": "HbA1c",
                "vitals": "Vitals",
                "misc_record": "Misc Record",
            }
            preview_fields.append(NLFieldPreview(
                label="Type",
                value=type_labels.get(record_type_raw, record_type_raw),
            ))
        except ValueError:
            pass

    if parsed.get("record_date"):
        preview_fields.append(NLFieldPreview(label="Date", value=parsed["record_date"]))

    if parsed.get("diagnosis"):
        preview_fields.append(NLFieldPreview(label="Diagnosis", value=parsed["diagnosis"]))

    if parsed.get("prescription_text"):
        preview_fields.append(NLFieldPreview(label="Rx", value=parsed["prescription_text"][:80]))

    rx_list = parsed.get("prescriptions")
    if isinstance(rx_list, list) and rx_list:
        preview_fields.append(NLFieldPreview(label="Medicines", value=str(len(rx_list))))

    lab_list = parsed.get("lab_tests")
    if isinstance(lab_list, list) and lab_list:
        preview_fields.append(NLFieldPreview(label="Lab Tests", value=str(len(lab_list))))

    if parsed.get("glucose_value"):
        preview_fields.append(NLFieldPreview(label="Glucose", value=f'{parsed["glucose_value"]} mg/dL'))

    if parsed.get("hba1c_value"):
        preview_fields.append(NLFieldPreview(label="HbA1c", value=f'{parsed["hba1c_value"]}%'))

    vitals_parts = []
    for key, label in [("weight", "Wt"), ("blood_pressure", "BP"), ("heart_rate", "HR"), ("temperature", "Temp")]:
        if parsed.get(key):
            vitals_parts.append(f"{label}: {parsed[key]}")
    if vitals_parts:
        preview_fields.append(NLFieldPreview(label="Vitals", value=", ".join(vitals_parts)))

    if parsed.get("clinical_notes") and len(preview_fields) < 4:
        preview_fields.append(NLFieldPreview(label="Notes", value=parsed["clinical_notes"][:60]))

    confidence = parsed.get("confidence", "medium")
    if member_match and member_match.matched_by == "default":
        confidence = "low"

    return NLParseResponse(
        member=member_match,
        record_type=record_type,
        record_date=parsed.get("record_date"),
        record_time=parsed.get("record_time"),
        diagnosis=parsed.get("diagnosis"),
        chief_complaint=parsed.get("chief_complaint"),
        existing_conditions=parsed.get("existing_conditions"),
        investigations=parsed.get("investigations"),
        provider_name=parsed.get("provider_name"),
        prescription_text=parsed.get("prescription_text"),
        prescriptions=parsed.get("prescriptions") if isinstance(parsed.get("prescriptions"), list) else None,
        lab_tests=parsed.get("lab_tests") if isinstance(parsed.get("lab_tests"), list) else None,
        clinical_notes=parsed.get("clinical_notes"),
        next_review_date=parsed.get("next_review_date"),
        glucose_value=_scalar(parsed.get("glucose_value")),
        meal_timing=parsed.get("meal_timing"),
        hba1c_value=_scalar(parsed.get("hba1c_value")),
        weight=_scalar(parsed.get("weight")),
        blood_pressure=parsed.get("blood_pressure"),
        heart_rate=_scalar(parsed.get("heart_rate")),
        temperature=_scalar(parsed.get("temperature")),
        confidence=confidence,
        preview_fields=preview_fields,
    )
