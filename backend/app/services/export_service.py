"""Export service — generate CSV exports of health data."""
import csv
import io
import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import HealthRecord, FamilyMember

logger = logging.getLogger(__name__)


def _parse_clinical_data(raw: str | None) -> dict | None:
    """Parse structured clinical_data JSON. Returns None if not structured."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed.get("_type") == "structured":
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return None


class ExportService:
    """Generate CSV exports for health data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_records_csv(
        self,
        household_id: UUID,
        member_id: UUID | None = None,
        record_type: str | None = None,
    ) -> str:
        """Export health records as CSV."""
        query = (
            select(HealthRecord, FamilyMember)
            .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
            .where(
                HealthRecord.household_id == str(household_id),
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
        )
        if member_id:
            query = query.where(HealthRecord.family_member_id == str(member_id))
        if record_type:
            query = query.where(HealthRecord.record_type == record_type)

        result = await self.db.execute(query)
        rows = result.all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Member", "Record Type", "Diagnosis",
            "Provider", "Chief Complaint", "Prescriptions",
            "Lab Tests", "Notes",
        ])

        for record, member in rows:
            parsed = _parse_clinical_data(record.clinical_data)
            prescriptions = ""
            lab_tests = ""
            chief_complaint = ""
            notes = ""

            if parsed:
                # Extract prescriptions
                for key in ("prescriptions", "medications"):
                    meds = parsed.get(key, [])
                    if meds and isinstance(meds, list):
                        prescriptions = "; ".join(
                            f"{m.get('medicine', '?')} {m.get('dosage', '')} {m.get('duration', '')}".strip()
                            for m in meds if isinstance(m, dict)
                        )

                # Extract lab tests
                for key in ("lab_results", "lab_tests"):
                    tests = parsed.get(key, [])
                    if tests and isinstance(tests, list):
                        lab_tests = "; ".join(
                            f"{t.get('test_name', '?')}: {t.get('result', '?')} {t.get('units', '')}".strip()
                            for t in tests if isinstance(t, dict)
                        )

                chief_complaint = parsed.get("chief_complaint", "")
                notes = parsed.get("_notes", "")

            writer.writerow([
                str(record.record_date) if record.record_date else "",
                f"{member.first_name} {member.last_name}",
                record.record_type or "",
                record.diagnosis or "",
                record.provider_name or "",
                chief_complaint,
                prescriptions,
                lab_tests,
                notes or (record.clinical_data or "" if not parsed else ""),
            ])

        return output.getvalue()

    async def export_medications_csv(
        self,
        household_id: UUID,
        member_id: UUID | None = None,
    ) -> str:
        """Export prescriptions/medications from health records as CSV."""
        query = (
            select(HealthRecord, FamilyMember)
            .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
            .where(
                HealthRecord.household_id == str(household_id),
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
        )
        if member_id:
            query = query.where(HealthRecord.family_member_id == str(member_id))

        result = await self.db.execute(query)
        rows = result.all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Member", "Record Type", "Medicine", "Type",
            "Dosage", "Duration", "Timing", "Note",
        ])

        for record, member in rows:
            parsed = _parse_clinical_data(record.clinical_data)
            if not parsed:
                continue

            member_name = f"{member.first_name} {member.last_name}"
            record_date = str(record.record_date) if record.record_date else ""

            # Extract prescriptions from table data
            for key in ("prescriptions", "medications"):
                meds = parsed.get(key, [])
                if not isinstance(meds, list):
                    continue
                for m in meds:
                    if not isinstance(m, dict):
                        continue
                    writer.writerow([
                        record_date,
                        member_name,
                        record.record_type or "",
                        m.get("medicine", ""),
                        m.get("type", ""),
                        m.get("dosage", ""),
                        m.get("duration", ""),
                        m.get("timing", ""),
                        m.get("note", ""),
                    ])

        return output.getvalue()

    async def export_lab_results_csv(
        self,
        household_id: UUID,
        member_id: UUID | None = None,
    ) -> str:
        """Export lab results as CSV — one row per test."""
        query = (
            select(HealthRecord, FamilyMember)
            .join(FamilyMember, HealthRecord.family_member_id == FamilyMember.id)
            .where(
                HealthRecord.household_id == str(household_id),
                HealthRecord.record_type.in_(["lab_report", "blood_glucose", "hba1c"]),
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
        )
        if member_id:
            query = query.where(HealthRecord.family_member_id == str(member_id))

        result = await self.db.execute(query)
        rows = result.all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Member", "Test Name", "Result", "Units",
            "Reference Range", "Status", "Record Type",
        ])

        for record, member in rows:
            parsed = _parse_clinical_data(record.clinical_data)
            member_name = f"{member.first_name} {member.last_name}"
            record_date = str(record.record_date) if record.record_date else ""

            if parsed:
                for key in ("lab_results", "lab_tests"):
                    tests = parsed.get(key, [])
                    if not isinstance(tests, list):
                        continue
                    for t in tests:
                        if not isinstance(t, dict):
                            continue
                        writer.writerow([
                            record_date,
                            member_name,
                            t.get("test_name", ""),
                            t.get("result", ""),
                            t.get("units", ""),
                            t.get("ref_value", ""),
                            t.get("note", ""),
                            record.record_type or "",
                        ])
                # Also check for glucose/hba1c fields
                if parsed.get("glucose_value"):
                    writer.writerow([
                        record_date, member_name, "Blood Glucose",
                        parsed["glucose_value"],
                        parsed.get("glucose_units", "mg/dL"),
                        "70-100", "", "blood_glucose",
                    ])
                if parsed.get("hba1c_value"):
                    writer.writerow([
                        record_date, member_name, "HbA1c",
                        parsed["hba1c_value"],
                        "%", "< 5.7%", "", "hba1c",
                    ])
            else:
                # Plain text record
                writer.writerow([
                    record_date, member_name, "(unstructured)",
                    "", "", "", record.diagnosis or "",
                    record.record_type or "",
                ])

        return output.getvalue()
