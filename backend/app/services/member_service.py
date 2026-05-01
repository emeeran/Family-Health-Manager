"""Family member service."""
import json
import logging
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.core.database import update_model
from app.models.base import FamilyMember, HealthRecord, RecordType, Gender, Relationship
from app.schemas.family_member import MedicalHistoryQuestionnaire

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
