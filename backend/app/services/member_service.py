"""Family member service."""
import asyncio
import json
import logging
from datetime import date, datetime, timezone, timedelta
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.core.database import update_model
from app.models.base import (
    AIInsight,
    FamilyMember,
    HealthRecord,
    ProviderAssignment,
    RecordType,
    Reminder,
    Vaccination,
    Gender,
    Relationship,
)
from app.schemas.family_member import FamilyMemberResponse, MedicalHistoryQuestionnaire
from app.schemas.provider_assignment import ProviderAssignmentResponse
from app.services.health_score_service import compute_health_score as _compute_health_score
from app.services.health_score_service import get_conditions_count, extract_hba1c_history

logger = logging.getLogger(__name__)


class MemberService:
    """Family member management service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def create_member(
        self,
        household_id: UUID,
        first_name: str,
        last_name: str,
        date_of_birth: datetime,
        gender: Gender,
        relationship: Relationship,
        medical_history: MedicalHistoryQuestionnaire | None = None,
        allergies: list[dict] | None = None,
        emergency_contact_name: str | None = None,
        emergency_contact_phone: str | None = None,
        height_cm: float | None = None,
        weight_kg: float | None = None,
    ) -> FamilyMember:
        """Create family member with optional medical history."""
        member = FamilyMember(
            household_id=household_id,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            gender=gender,
            relationship_type=relationship,
            height_cm=height_cm,
            weight_kg=weight_kg,
            emergency_contact_name=emergency_contact_name,
            emergency_contact_phone=emergency_contact_phone,
        )

        if allergies:
            member.allergies_json = json.dumps(allergies)

        if medical_history:
            parts = {
                "Conditions": medical_history.conditions,
                "Allergies": medical_history.allergies,
                "Medications": medical_history.current_medications,
                "Surgeries": medical_history.past_surgeries,
            }
            member.medical_history_summary = "; ".join(
                f"{k}: {v}" for k, v in parts.items() if v
            ) or None
            member.blood_group = medical_history.blood_group
            member.family_history = medical_history.family_history

        self.db.add(member)
        await self.db.flush()
        return member

    async def get_member(self, household_id: UUID, member_id: UUID) -> FamilyMember:
        """Get member by ID, ensuring household access."""
        result = await self.db.execute(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.household_id == household_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ValueError("Member not found")
        return member

    async def list_members(
        self, household_id: UUID, is_active: bool | None = None
    ) -> list[FamilyMember]:
        """List all members in household."""
        query = select(FamilyMember).where(FamilyMember.household_id == household_id)
        if is_active is not None:
            query = query.where(FamilyMember.is_active == is_active)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_member(self, member_id: UUID, **kwargs) -> FamilyMember:
        """Update member fields. Auto-logs a VITALS record if height/weight changes."""
        allowed = {
            "first_name", "last_name", "date_of_birth", "gender",
            "relationship_type", "height_cm", "weight_kg",
            "emergency_contact_name", "emergency_contact_phone",
            "blood_group", "family_history", "medical_history_summary",
            "allergies_json",
        }
        result = await self.db.execute(
            select(FamilyMember).where(FamilyMember.id == member_id)
        )
        member = result.scalar_one()

        old_h, old_w = member.height_cm, member.weight_kg
        member = await update_model(self.db, member, allowed_fields=allowed, **kwargs)

        h = kwargs.get("height_cm", old_h)
        w = kwargs.get("weight_kg", old_w)
        h_changed = h != old_h
        w_changed = w != old_w

        if (h_changed or w_changed) and h and w and h > 0:
            hm = h / 100
            bmi = round(w / (hm * hm), 1)
            vitals_record = HealthRecord(
                family_member_id=member_id,
                record_type=RecordType.VITALS,
                record_date=datetime.now(timezone.utc).date(),
                clinical_data=json.dumps({
                    "_type": "structured",
                    "bmi": bmi,
                    "height_cm": h,
                    "weight_kg": w,
                }),
            )
            self.db.add(vitals_record)

        return member

    async def soft_delete_member(self, household_id: UUID, member_id: UUID) -> None:
        """Soft-delete a member."""
        member = await self.get_member(household_id, member_id)
        member.is_active = False
        await self.db.flush()

    async def get_active_medications(self, member_id: UUID) -> list[dict]:
        """Get current medications for a member.

        Queries ALL non-deleted DOCTOR_VISIT records ordered by date DESC,
        returns every prescription from every visit. No dedup — each
        prescription is tied to a specific record and provider.
        """
        result = await self.db.execute(
            select(HealthRecord)
            .options(joinedload(HealthRecord.provider))
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_type == RecordType.DOCTOR_VISIT,
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        )
        records = result.scalars().unique().all()

        medications: list[dict] = []

        for r in records:
            if not r.clinical_data:
                continue

            prescriptions: list[dict] = []
            try:
                parsed = json.loads(r.clinical_data)
                if isinstance(parsed, dict) and parsed.get("_type") == "structured":
                    if parsed.get("_medication_sync") is False:
                        continue
                    rx_list = parsed.get("prescriptions", [])
                    if isinstance(rx_list, list):
                        prescriptions = rx_list
            except (json.JSONDecodeError, ValueError):
                pass

            if not prescriptions and r.prescription_text:
                for line in r.prescription_text.strip().split("\n"):
                    line = line.strip()
                    if line:
                        prescriptions.append({"medicine": line})

            for rx_idx, rx in enumerate(prescriptions):
                med_name = rx.get("medicine", "").strip()
                if not med_name:
                    continue

                medications.append({
                    "medicine": med_name,
                    "type": rx.get("type", ""),
                    "dosage": rx.get("dosage", ""),
                    "duration": rx.get("duration", ""),
                    "timing": rx.get("timing", ""),
                    "note": rx.get("note", ""),
                    "prescribed_date": r.record_date.isoformat() if r.record_date else None,
                    "provider_name": r.provider.name if r.provider else None,
                    "record_id": str(r.id),
                    "prescription_index": rx_idx,
                })

        return medications

    async def get_member_detail(self, household_id: UUID, member_id: UUID) -> dict:
        """Return aggregated member detail for the detail page.

        Runs all independent queries in parallel via asyncio.gather.
        """
        from app.services.preventive_care_service import PreventiveCareService

        member = await self.get_member(household_id, member_id)

        today = date.today()
        age = today.year - member.date_of_birth.year - (
            (today.month, today.day) < (member.date_of_birth.month, member.date_of_birth.day)
        )
        conditions_count = get_conditions_count(member.medical_history_summary)

        (
            active_medications,
            recent_records_raw,
            assignments_result,
            hba1c_history,
            drug_interactions,
            latest_insight,
            preconsult_note,
            smart_report,
            reminders_result,
            vaccinations_result,
            preventive_recs,
        ) = await asyncio.gather(
            self.get_active_medications(member_id),
            self._detail_recent_records(member_id),
            self._detail_provider_assignments(member_id, member),
            self._detail_hba1c_history(member_id),
            self._detail_drug_interactions(member_id),
            self._detail_latest_insight(member_id),
            self._detail_latest_preconsult(member_id),
            self._detail_latest_smart_report(member_id),
            self._detail_upcoming_reminders(member_id),
            self._detail_vaccinations(member_id),
            PreventiveCareService(self.db).generate_recommendations(member),
        )

        recent_records = list(recent_records_raw)
        health_score, score_breakdown = _compute_health_score(
            member, conditions_count, active_medications, recent_records, age
        )

        risk_level = "high" if health_score < 40 else "moderate" if health_score <= 65 else "low"

        return {
            "member": FamilyMemberResponse.model_validate(member).model_dump(mode="json"),
            "health_score": health_score,
            "score_breakdown": score_breakdown,
            "brief_medical_history": member.medical_history_summary,
            "active_medications": active_medications,
            "active_medications_count": len(active_medications),
            "active_conditions_count": conditions_count,
            "age": age,
            "provider_assignments": assignments_result,
            "risk_assessment": {"level": risk_level, "score": health_score},
            "hba1c_history": hba1c_history,
            "drug_interactions": drug_interactions,
            "latest_insight": latest_insight,
            "latest_preconsult_note": preconsult_note,
            "latest_smart_report": smart_report,
            "recent_records": self._serialize_recent_records(recent_records),
            "upcoming_reminders": reminders_result,
            "vaccinations": vaccinations_result,
            "preventive_recommendations": preventive_recs,
        }

    # ── Private detail helpers ──

    async def _detail_recent_records(self, member_id: UUID) -> list[HealthRecord]:
        result = await self.db.execute(
            select(HealthRecord)
            .options(joinedload(HealthRecord.provider))
            .where(HealthRecord.family_member_id == member_id, HealthRecord.is_deleted.is_(False))
            .order_by(HealthRecord.record_date.desc())
            .limit(20)
        )
        return list(result.scalars().all())

    @staticmethod
    def _serialize_recent_records(records: list[HealthRecord]) -> list[dict]:
        return [
            {
                "id": str(r.id),
                "record_type": r.record_type.value if hasattr(r.record_type, "value") else r.record_type,
                "record_date": r.record_date.isoformat() if r.record_date else None,
                "diagnosis": r.diagnosis,
                "provider_name": r.provider_name,
                "clinical_data": r.clinical_data,
            }
            for r in records
        ]

    async def _detail_provider_assignments(self, member_id: UUID, member: FamilyMember) -> list[dict]:
        result = await self.db.execute(
            select(ProviderAssignment)
            .options(joinedload(ProviderAssignment.provider))
            .where(ProviderAssignment.family_member_id == member_id)
            .order_by(ProviderAssignment.created_at.desc())
        )
        out: list[dict] = []
        for a in result.scalars().unique().all():
            out.append(
                ProviderAssignmentResponse(
                    id=a.id, provider_id=a.provider_id,
                    provider_name=a.provider.name if a.provider else "Unknown",
                    family_member_id=a.family_member_id,
                    family_member_name=f"{member.first_name} {member.last_name}",
                    uhid=a.uhid, created_at=a.created_at,
                ).model_dump(mode="json")
            )
        return out

    async def _detail_hba1c_history(self, member_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(HealthRecord)
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_type.in_([RecordType.BLOOD_GLUCOSE, RecordType.DOCTOR_VISIT, RecordType.LAB_REPORT]),
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.asc())
        )
        return extract_hba1c_history(list(result.scalars().all()))

    async def _detail_drug_interactions(self, member_id: UUID) -> list[dict]:
        medications = await self.get_active_medications(member_id)
        if len(medications) < 2:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await self.db.execute(
            select(AIInsight)
            .where(AIInsight.prompt == f"__drug_interactions__{member_id}", AIInsight.generated_at >= cutoff)
            .order_by(AIInsight.generated_at.desc()).limit(1)
        )
        cached = result.scalar_one_or_none()
        if cached:
            try:
                interactions = json.loads(cached.response)
                if isinstance(interactions, list):
                    return interactions
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    async def _detail_latest_insight(self, member_id: UUID) -> dict | None:
        result = await self.db.execute(
            select(AIInsight)
            .where(
                AIInsight.prompt.notlike("__drug_interactions__%"),
                AIInsight.prompt.notlike("__preconsult__%"),
                AIInsight.prompt.notlike("__smartreport__%"),
            )
            .order_by(AIInsight.generated_at.desc()).limit(1)
        )
        insight = result.scalar_one_or_none()
        if not insight:
            return None
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
            } if insight.verification_status != "pending" or insight.verification_at else {"status": "pending" if (datetime.now(timezone.utc) - insight.generated_at.replace(tzinfo=timezone.utc)).total_seconds() < 300 else "unverifiable"},
        }

    async def _detail_latest_preconsult(self, member_id: UUID) -> dict | None:
        result = await self.db.execute(
            select(AIInsight)
            .where(AIInsight.prompt.like(f"__preconsult__{member_id}__%"), AIInsight.health_record_id.is_(None))
            .order_by(AIInsight.generated_at.desc()).limit(1)
        )
        insight = result.scalar_one_or_none()
        if not insight:
            return None
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
            } if insight.verification_status != "pending" or insight.verification_at else {"status": "pending" if (datetime.now(timezone.utc) - insight.generated_at.replace(tzinfo=timezone.utc)).total_seconds() < 300 else "unverifiable"},
        }

    async def _detail_latest_smart_report(self, member_id: UUID) -> dict | None:
        result = await self.db.execute(
            select(AIInsight)
            .where(AIInsight.prompt.like(f"__smartreport__{member_id}__%"), AIInsight.health_record_id.is_(None))
            .order_by(AIInsight.generated_at.desc()).limit(1)
        )
        insight = result.scalar_one_or_none()
        if not insight:
            return None
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
            } if insight.verification_status != "pending" or insight.verification_at else {"status": "pending" if (datetime.now(timezone.utc) - insight.generated_at.replace(tzinfo=timezone.utc)).total_seconds() < 300 else "unverifiable"},
        }

    async def _detail_upcoming_reminders(self, member_id: UUID) -> list[dict]:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Reminder)
            .where(Reminder.family_member_id == member_id, Reminder.is_active.is_(True), Reminder.start_datetime >= now)
            .order_by(Reminder.start_datetime.asc()).limit(10)
        )
        return [
            {"id": str(r.id), "title": r.title, "description": r.description,
             "start_datetime": r.start_datetime.isoformat() if r.start_datetime else None,
             "reminder_type": r.reminder_type.value if hasattr(r.reminder_type, "value") else r.reminder_type}
            for r in result.scalars().all()
        ]

    async def _detail_vaccinations(self, member_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(Vaccination).where(Vaccination.family_member_id == member_id)
            .order_by(Vaccination.date_administered.desc())
        )
        return [
            {"id": str(v.id), "name": v.name,
             "date_administered": v.date_administered.isoformat() if v.date_administered else None,
             "booster_due_date": v.booster_due_date.isoformat() if v.booster_due_date else None,
             "notes": v.notes}
            for v in result.scalars().all()
        ]
