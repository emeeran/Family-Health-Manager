"""Context builder — constructs AI prompts from patient records and member data."""
import json
import logging
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FamilyMember, HealthRecord

logger = logging.getLogger(__name__)


async def build_member_context(
    db: AsyncSession, member_id: UUID, fmt_date, comprehensive: bool = False
) -> str:
    """Build comprehensive medical history context for AI prompt."""
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.id == member_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        return ""

    # --- Patient Profile ---
    today = date.today()
    age = today.year - member.date_of_birth.year - (
        (today.month, today.day) < (member.date_of_birth.month, member.date_of_birth.day)
    )
    context = f"Patient: {member.first_name} {member.last_name} (Age: {age})\n"
    context += f"Date of Birth: {fmt_date(member.date_of_birth)}\n"
    context += f"Gender: {member.gender.value}\n"

    if member.blood_group:
        context += f"Blood Group: {member.blood_group}\n"

    # Physical metrics + BMI
    if member.height_cm and member.weight_kg and member.height_cm > 0:
        hm = member.height_cm / 100
        bmi = round(member.weight_kg / (hm * hm), 1)
        context += f"Height: {member.height_cm} cm, Weight: {member.weight_kg} kg, BMI: {bmi}\n"
    elif member.height_cm:
        context += f"Height: {member.height_cm} cm\n"
    elif member.weight_kg:
        context += f"Weight: {member.weight_kg} kg\n"

    # Allergies
    if member.allergies_json:
        try:
            allergies = json.loads(member.allergies_json)
            if isinstance(allergies, list) and allergies:
                allergy_lines = []
                for a in allergies:
                    if isinstance(a, dict):
                        name = a.get("name") or a.get("allergy") or ""
                        severity = a.get("severity") or a.get("reaction") or ""
                        line = name
                        if severity:
                            line += f" ({severity})"
                        if line:
                            allergy_lines.append(line)
                    elif isinstance(a, str) and a:
                        allergy_lines.append(a)
                if allergy_lines:
                    context += f"Allergies: {'; '.join(allergy_lines)}\n"
        except (json.JSONDecodeError, ValueError):
            pass

    if member.medical_history_summary:
        context += f"Medical History: {member.medical_history_summary}\n"
    if member.family_history:
        context += f"Family Medical History: {member.family_history}\n"

    # --- Health Records ---
    query = (
        select(HealthRecord)
        .options(selectinload(HealthRecord.provider))
        .where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
    )
    query = query.limit(20 if comprehensive else 5)

    recent = await db.execute(query)
    records = list(recent.scalars().all())

    # Aggregate across records for summary sections
    all_diagnoses: list[str] = []
    all_providers: list[str] = []
    overdue_followups: list[str] = []

    if records:
        label = "All Health Records" if comprehensive else "Recent Records"
        context += f"\n{label} ({len(records)} records):\n"
        for r in records:
            # Track diagnoses
            if r.diagnosis and r.diagnosis.strip():
                all_diagnoses.append(r.diagnosis.strip())

            # Track providers
            if r.provider_name and r.provider_name.strip():
                pname = r.provider_name.strip()
                if pname not in all_providers:
                    all_providers.append(pname)

            # Track overdue follow-ups
            if r.next_review_date and r.next_review_date < today:
                overdue_followups.append(
                    f"[{fmt_date(r.next_review_date)}] {r.record_type.value}"
                    + (f" — {r.diagnosis}" if r.diagnosis else "")
                )

            rec_line = f"- [{fmt_date(r.record_date)}] {r.record_type.value}"
            if r.diagnosis:
                rec_line += f" — {r.diagnosis}"
            summary = summarize_clinical_data(r.clinical_data)
            if summary:
                rec_line += f"\n  {summary[:500]}"
            if r.prescription_text:
                rec_line += f"\n  Rx: {r.prescription_text[:300]}"
            if r.provider_name:
                rec_line += f"\n  Provider: {r.provider_name}"
            if r.next_review_date:
                rec_line += f"\n  Next Review: {fmt_date(r.next_review_date)}"
            context += rec_line + "\n"

    # --- Aggregated Summary Sections ---

    # All diagnoses (deduplicated)
    unique_diagnoses = list(dict.fromkeys(all_diagnoses))
    if unique_diagnoses:
        context += f"\n=== ALL DIAGNOSES ({len(unique_diagnoses)}) ===\n"
        for d in unique_diagnoses:
            context += f"  - {d}\n"

    # All providers
    if all_providers:
        context += f"\n=== PROVIDERS ({len(all_providers)}) ===\n"
        for p in all_providers:
            context += f"  - {p}\n"

    # Overdue follow-ups
    if overdue_followups:
        context += f"\n=== OVERDUE FOLLOW-UPS ({len(overdue_followups)}) ===\n"
        for f in overdue_followups:
            context += f"  - {f}\n"

    # Aggregate ALL medications across ALL records (not limited by record cap)
    med_summary = await build_medication_summary(db, member_id)
    if med_summary:
        context += f"\n{med_summary}\n"

    # Key lab trends
    if records:
        lab_trends = build_lab_trends_from_records(records)
        if lab_trends:
            context += lab_trends

    return context


async def build_medication_summary(db: AsyncSession, member_id: UUID) -> str:
    """Aggregate all medications for a member using MedicationService + prescription_text."""
    from app.models.base import RecordType
    from app.services.medication_service import MedicationService

    med_svc = MedicationService(db)
    all_meds: dict[str, str] = {}  # normalized_name -> formatted line

    # 1. Use MedicationService for structured, deduplicated active medications
    #    This already queries all DOCTOR_VISIT records.
    try:
        active_meds = await med_svc.get_active_medications(member_id)
        for med in active_meds:
            name = med.get("medicine", "").strip()
            if not name:
                continue
            key = name.strip().lower().split()[0]
            dtype = med.get("type", "")
            dosage = med.get("dosage", "")
            timing = med.get("timing", "")
            line = f"{dtype} {name} {dosage}".strip()
            if timing:
                line += f" ({timing})"
            status = med.get("status", "")
            if status:
                line += f" [{status}]"
            all_meds[key] = line
    except Exception as exc:
        logger.warning("MedicationService failed for summary: %s", exc)

    # 2. Scan non-DOCTOR_VISIT records for additional prescriptions.
    #    DOCTOR_VISIT records are already fully handled by MedicationService above,
    #    so we exclude them to avoid the redundant query.
    result = await db.execute(
        select(HealthRecord.clinical_data, HealthRecord.prescription_text)
        .where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.record_type != RecordType.DOCTOR_VISIT,
            HealthRecord.is_deleted.is_(False),
        )
    )
    for clinical_data, prescription_text in result.all():
        # Structured prescriptions from non-doctor_visit record types
        if clinical_data:
            try:
                data = json.loads(clinical_data)
                if isinstance(data, dict):
                    rx = data.get("prescriptions")
                    if rx and isinstance(rx, list):
                        for p in rx:
                            if not isinstance(p, dict):
                                continue
                            med_name = (p.get("medicine") or "").strip()
                            if not med_name:
                                continue
                            key = med_name.strip().lower().split()[0]
                            if key in all_meds:
                                continue
                            dtype = p.get("type", "")
                            dosage = p.get("dosage", "")
                            timing = p.get("timing", "")
                            line = f"{dtype} {med_name} {dosage}".strip()
                            if timing:
                                line += f" ({timing})"
                            all_meds[key] = line
            except (json.JSONDecodeError, ValueError):
                pass

        # Free-text prescriptions (handle multiple separators)
        if prescription_text:
            import re as _re
            for line in _re.split(r"[;\n]+", prescription_text):
                line = line.strip()
                if not line or len(line) < 3:
                    continue
                key = line.lower().split()[0] if line.split() else ""
                if key and key not in all_meds:
                    all_meds[key] = line

    if not all_meds:
        return ""

    lines = [f"=== ALL CURRENT MEDICATIONS ({len(all_meds)} medications) ==="]
    for med_line in sorted(all_meds.values()):
        lines.append(f"  - {med_line}")
    return "\n".join(lines)


async def build_household_context(
    db: AsyncSession, household_id: UUID, fmt_date
) -> str:
    """Build health context for an entire household (all members + recent records)."""
    # Fetch all active members
    members_result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.household_id == household_id,
        )
    )
    members = list(members_result.scalars().all())

    if not members:
        return ""

    # Single query for all members' records (avoids N+1)
    member_ids = [m.id for m in members]
    all_records_result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.family_member_id.in_(member_ids),
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
        .limit(200)
    )
    all_records = list(all_records_result.scalars().all())

    # Group records by member
    records_by_member: dict[UUID, list[HealthRecord]] = {}
    for r in all_records:
        records_by_member.setdefault(r.family_member_id, []).append(r)

    context = "=== FAMILY HEALTH SUMMARY ===\n\n"

    for member in members:
        context += f"--- {member.first_name} {member.last_name} ---\n"
        context += f"DOB: {fmt_date(member.date_of_birth)}\n"
        context += f"Gender: {member.gender.value}\n"
        if member.medical_history_summary:
            context += f"Conditions: {member.medical_history_summary}\n"
        if member.blood_group:
            context += f"Blood Group: {member.blood_group}\n"

        records = records_by_member.get(member.id, [])[:15]
        if records:
            context += f"Records ({len(records)}):\n"
            for r in records:
                rec_line = f"  [{fmt_date(r.record_date)}] {r.record_type.value}"
                if r.diagnosis:
                    rec_line += f" — {r.diagnosis}"
                summary = summarize_clinical_data(r.clinical_data)
                if summary:
                    rec_line += f"\n    {summary[:200]}"
                if r.prescription_text:
                    rec_line += f"\n    Rx: {r.prescription_text[:150]}"
                context += rec_line + "\n"
        context += "\n"

    # Key Lab Trends — extract HbA1c, glucose, cholesterol across ALL records
    context += build_lab_trends_from_records(all_records)

    return context


def build_lab_trends_from_records(records: list) -> str:
    """Build a summary of key lab test trends from pre-fetched records (no DB queries)."""
    KEY_TESTS = {
        "hba1c": "HbA1c",
        "hb a1c": "HbA1c",
        "glycosylated": "HbA1c",
        "fasting glucose": "Fasting Glucose",
        "postprandial": "Postprandial Glucose",
        "total cholesterol": "Total Cholesterol",
        "ldl cholesterol": "LDL Cholesterol",
        "hdl cholesterol": "HDL Cholesterol",
        "triglyceride": "Triglycerides",
    }

    trends: dict[str, list[tuple[str, str, str]]] = {}

    for r in records:
        if not r.clinical_data:
            continue
        try:
            data = json.loads(r.clinical_data)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key in ("tests", "lab_results"):
            for t in data.get(key, []) or []:
                if not isinstance(t, dict):
                    continue
                name = (t.get("test_name") or "").lower()
                result = str(t.get("result", ""))
                note = t.get("note", "")
                for kw, canonical in KEY_TESTS.items():
                    if kw in name:
                        date_str = str(r.record_date)
                        trends.setdefault(canonical, []).append(
                            (date_str, result, note)
                        )
                        break

    if not trends:
        return ""

    lines = ["\n=== KEY LAB TRENDS (all dates) ==="]
    for test_name, entries in sorted(trends.items()):
        lines.append(f"\n{test_name}:")
        for date_str, result, note in entries:
            line = f"  {date_str}: {result}"
            if note:
                line += f" ({note})"
            lines.append(line)

    return "\n".join(lines) + "\n"


def summarize_clinical_data(raw: str | None) -> str:
    """Extract key information from structured clinical JSON for AI context."""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return f"Data: {raw[:500]}"

    if not isinstance(data, dict) or data.get("_type") != "structured":
        return f"Data: {raw[:500]}"

    parts: list[str] = []

    # Chief complaint
    if data.get("chief_complaint"):
        parts.append(f"Complaint: {data['chief_complaint']}")

    # Existing conditions
    if data.get("existing_conditions"):
        parts.append(f"Existing Conditions: {data['existing_conditions']}")

    # Lab tests / results (from both 'tests' and 'lab_results' keys)
    for key in ("tests", "lab_results"):
        tests = data.get(key)
        if tests and isinstance(tests, list):
            for t in tests:
                if not isinstance(t, dict):
                    continue
                name = t.get("test_name", "")
                result = t.get("result", "")
                ref = t.get("ref_value", "")
                note = t.get("note", "")
                line = f"{name}: {result}"
                if ref:
                    line += f" (ref: {ref})"
                if note:
                    line += f" — {note}"
                parts.append(line)

    # Prescriptions (from structured clinical_data)
    rx = data.get("prescriptions")
    if rx and isinstance(rx, list):
        rx_items = []
        for p in rx:
            if not isinstance(p, dict):
                continue
            med = p.get("medicine", "")
            dtype = p.get("type", "")
            dosage = p.get("dosage", "")
            timing = p.get("timing", "")
            note = p.get("note", "")
            line = f"{dtype} {med} {dosage}".strip()
            if timing:
                line += f" ({timing})"
            if note:
                line += f" [{note}]"
            rx_items.append(line)
        if rx_items:
            parts.append("Prescriptions: " + "; ".join(rx_items))

    # Investigations
    if data.get("investigations"):
        parts.append(f"Investigations: {data['investigations']}")

    # Clinical notes (free text)
    if data.get("clinical_data"):
        parts.append(f"Notes: {str(data['clinical_data'])[:200]}")

    return "\n    ".join(parts)


async def build_record_context(db: AsyncSession, record_id: UUID, fmt_date) -> str:
    """Build context from health record."""
    result = await db.execute(
        select(HealthRecord).where(HealthRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        return ""

    context = f"\nHealth Record ({record.record_type.value}):\n"
    context += f"Date: {fmt_date(record.record_date)}\n"
    context += f"Data: {(record.clinical_data or '')[:500]}\n"
    if record.diagnosis:
        context += f"Diagnosis: {record.diagnosis}\n"
    return context


def fmt_date(d: object) -> str:
    """Format a date for AI context in an unambiguous, human-readable way."""
    if d is None:
        return "N/A"
    s = str(d)
    try:
        parsed = datetime.strptime(s[:10], "%Y-%m-%d")
        return parsed.strftime("%d-%b-%Y")  # e.g. "09-Apr-2026"
    except (ValueError, TypeError):
        return s
