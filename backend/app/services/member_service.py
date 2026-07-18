"""Family member service."""

import asyncio
import json
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID
from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from app.core.database import update_model
from app.models.base import (
    AIInsight,
    Conversation,
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
from app.schemas.insight_serializers import (
    serialize_insight_payload,
    serialize_smart_report_payload,
)
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
        patient_id: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        height_cm: float | None = None,
        weight_kg: float | None = None,
        notes: str | None = None,
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
            patient_id=patient_id,
            phone=phone,
            address=address,
            notes=notes,
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
            member.medical_history_summary = (
                "; ".join(f"{k}: {v}" for k, v in parts.items() if v) or None
            )
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
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "relationship_type",
            "height_cm",
            "weight_kg",
            "emergency_contact_name",
            "emergency_contact_phone",
            "patient_id",
            "phone",
            "address",
            "blood_group",
            "family_history",
            "medical_history_summary",
            "allergies_json",
            "notes",
        }
        result = await self.db.execute(select(FamilyMember).where(FamilyMember.id == member_id))
        member = result.scalar_one()

        old_h, old_w = member.height_cm, member.weight_kg
        member = await update_model(self.db, member, allowed_fields=allowed, **kwargs)

        h = kwargs.get("height_cm", old_h)
        w = kwargs.get("weight_kg", old_w)
        h_changed = h != old_h
        w_changed = w != old_w

        if (h_changed or w_changed) and h and w and h > 0:
            payload = self._build_vitals_payload(height_cm=h, weight_kg=w)
            if payload is not None:
                self.db.add(
                    HealthRecord(
                        family_member_id=member_id,
                        record_type=RecordType.VITALS,
                        record_date=datetime.now(timezone.utc).date(),
                        clinical_data=json.dumps(payload),
                    )
                )

        return member

    # Allowed MIME types for a profile photo. Stricter than storage's set
    # (which also permits PDFs) — a face photo must be an image.
    PHOTO_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

    async def set_member_photo(
        self,
        member_id: UUID,
        file: UploadFile,
        household_id: UUID,
        background_tasks: BackgroundTasks | None = None,
    ) -> FamilyMember:
        """Upload or replace a member's profile photo.

        Reuses content-addressable encrypted storage (``save_file_hashed``) and
        generates a 300px WebP thumbnail synchronously — a single small image,
        so no need to defer it to a background task. Replacing a photo
        reference-counts the previous blob so a file dedup-shared with another
        member or a health-record attachment is only removed when nothing else
        references it.
        """
        from app.core.storage import save_file_hashed
        from app.core.thumbnails import generate_thumbnail

        member = await self.get_member(household_id, member_id)

        mime = file.content_type or "application/octet-stream"
        if mime not in self.PHOTO_MIME_TYPES:
            raise ValueError(f"Photo must be jpeg, png, or webp (got {mime})")

        old_hash = member.photo_content_hash
        old_photo_path = member.photo_path
        old_thumb_path = member.photo_thumbnail_path

        file_path, content_hash, _ext = await save_file_hashed(file)
        thumbnail_path = await generate_thumbnail(file_path, content_hash, mime, encrypted=True)

        member.photo_path = str(file_path)
        member.photo_content_hash = content_hash
        member.photo_thumbnail_path = str(thumbnail_path) if thumbnail_path else None
        member.photo_updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        if old_hash and old_hash != content_hash:
            await self._delete_photo_blob_if_unreferenced(
                old_hash, old_photo_path, old_thumb_path, background_tasks=background_tasks
            )

        return member

    async def delete_member_photo(
        self,
        member_id: UUID,
        household_id: UUID,
        background_tasks: BackgroundTasks | None = None,
    ) -> FamilyMember:
        """Remove a member's profile photo (reference-counted file delete)."""
        member = await self.get_member(household_id, member_id)

        old_hash = member.photo_content_hash
        old_photo_path = member.photo_path
        old_thumb_path = member.photo_thumbnail_path

        member.photo_path = None
        member.photo_content_hash = None
        member.photo_thumbnail_path = None
        member.photo_updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        if old_hash:
            await self._delete_photo_blob_if_unreferenced(
                old_hash, old_photo_path, old_thumb_path, background_tasks=background_tasks
            )

        return member

    async def _delete_photo_blob_if_unreferenced(
        self,
        content_hash: str,
        photo_path: str | None,
        thumb_path: str | None,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        """Delete a photo's physical files only if nothing else references them.

        A photo blob is content-addressed and may be dedup-shared with another
        member's photo or with a health-record attachment, so count both before
        removing the stored file and its thumbnail.
        """
        from app.core.storage import delete_file
        from app.models.base import Attachment

        members_count = (
            await self.db.execute(
                select(func.count())
                .select_from(FamilyMember)
                .where(FamilyMember.photo_content_hash == content_hash)
            )
        ).scalar()
        attachments_count = (
            await self.db.execute(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.content_hash == content_hash)
            )
        ).scalar()

        if (members_count or 0) + (attachments_count or 0) > 0:
            return

        # Physical deletion is deferred to a BackgroundTask when supplied so a
        # transaction rollback can't orphan the file (row restored pointing at
        # deleted bytes). delete_file is already tolerant of a missing file, so
        # the old FileNotFoundError handling is no longer needed.
        to_delete: list[Path] = []
        if photo_path:
            to_delete.append(Path(photo_path))
        if thumb_path:
            to_delete.append(Path(thumb_path))
        for path in to_delete:
            if background_tasks is not None:
                background_tasks.add_task(delete_file, path)
            else:
                await delete_file(path)

    @staticmethod
    def _build_vitals_payload(
        *,
        height_cm: float | None = None,
        weight_kg: float | None = None,
        blood_pressure: str | None = None,
        heart_rate: str | None = None,
        temperature: str | None = None,
        source_visit_id: UUID | None = None,
    ) -> dict | None:
        """Build the structured clinical_data dict for a VITALS record.

        Keys match what the BMI-history reader (member_history) expects
        (bmi/height_cm/weight_kg) plus blood_pressure/heart_rate/temperature.
        Returns None if no vital values are present.
        """
        payload: dict[str, object] = {"_type": "structured"}
        if height_cm and weight_kg and height_cm > 0:
            hm = height_cm / 100
            payload["bmi"] = round(weight_kg / (hm * hm), 1)
        if height_cm is not None:
            payload["height_cm"] = height_cm
        if weight_kg is not None:
            payload["weight_kg"] = weight_kg
        if blood_pressure:
            payload["blood_pressure"] = blood_pressure
        if heart_rate:
            payload["heart_rate"] = heart_rate
        if temperature:
            payload["temperature"] = temperature
        if source_visit_id is not None:
            payload["_source_visit"] = str(source_visit_id)
        vital_keys = {
            "bmi",
            "height_cm",
            "weight_kg",
            "blood_pressure",
            "heart_rate",
            "temperature",
        }
        if not (vital_keys & payload.keys()):
            return None
        return payload

    async def sync_vitals_from_visit(
        self,
        member_id: UUID,
        record_date: date,
        vitals: dict,
        source_visit_id: UUID,
    ) -> None:
        """Sync vitals from a doctor-visit record into the member profile + a VITALS record.

        ``vitals`` maps the frontend custom-field keys (weight, height,
        blood_pressure, heart_rate, temperature) to their string values. Updates
        the member's current height/weight directly (NOT via update_member, to
        avoid its auto-VITALS duplicate), then writes exactly one VITALS record
        tagged with the source visit so BMI/vitals history includes the visit and
        edits update in place rather than creating duplicates.
        """

        def _fnum(val: object) -> float | None:
            if val is None:
                return None
            try:
                return float(str(val).strip())
            except (TypeError, ValueError):
                return None

        def _fstr(val: object) -> str | None:
            if val is None:
                return None
            s = str(val).strip()
            return s or None

        weight_kg = _fnum(vitals.get("weight"))
        height_cm = _fnum(vitals.get("height"))
        blood_pressure = _fstr(vitals.get("blood_pressure"))
        heart_rate = _fstr(vitals.get("heart_rate"))
        temperature = _fstr(vitals.get("temperature"))

        if not any(
            v is not None for v in (weight_kg, height_cm, blood_pressure, heart_rate, temperature)
        ):
            return

        payload = self._build_vitals_payload(
            height_cm=height_cm,
            weight_kg=weight_kg,
            blood_pressure=blood_pressure,
            heart_rate=heart_rate,
            temperature=temperature,
            source_visit_id=source_visit_id,
        )
        if payload is None:
            return

        # Update member's current profile values (skip update_member's auto-VITALS).
        result = await self.db.execute(select(FamilyMember).where(FamilyMember.id == member_id))
        member = result.scalar_one_or_none()
        if member is not None:
            if height_cm is not None:
                member.height_cm = height_cm
            if weight_kg is not None:
                member.weight_kg = weight_kg

        # Update-or-create: find an existing VITALS record tagged to this visit.
        existing: HealthRecord | None = None
        res = await self.db.execute(
            select(HealthRecord).where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_type == RecordType.VITALS,
                HealthRecord.is_deleted.is_(False),
            )
        )
        for rec in res.scalars().all():
            try:
                if json.loads(rec.clinical_data or "{}").get("_source_visit") == str(
                    source_visit_id
                ):
                    existing = rec
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        if existing is not None:
            existing.clinical_data = json.dumps(payload)
            existing.record_date = record_date
        else:
            self.db.add(
                HealthRecord(
                    family_member_id=member_id,
                    record_type=RecordType.VITALS,
                    record_date=record_date,
                    clinical_data=json.dumps(payload),
                )
            )

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

                medications.append(
                    {
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
                    }
                )

        return medications

    async def get_member_detail(self, household_id: UUID, member_id: UUID) -> dict:
        """Return aggregated member detail for the detail page.

        Runs all independent queries in parallel via asyncio.gather.
        """
        from app.services.preventive_care_service import PreventiveCareService

        member = await self.get_member(household_id, member_id)

        today = date.today()
        age = (
            today.year
            - member.date_of_birth.year
            - ((today.month, today.day) < (member.date_of_birth.month, member.date_of_birth.day))
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
                "record_type": r.record_type.value
                if hasattr(r.record_type, "value")
                else r.record_type,
                "record_date": r.record_date.isoformat() if r.record_date else None,
                "diagnosis": r.diagnosis,
                "provider_name": r.provider_name,
                "clinical_data": r.clinical_data,
            }
            for r in records
        ]

    async def _detail_provider_assignments(
        self, member_id: UUID, member: FamilyMember
    ) -> list[dict]:
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
                    id=a.id,
                    provider_id=a.provider_id,
                    provider_name=a.provider.name if a.provider else "Unknown",
                    family_member_id=a.family_member_id,
                    family_member_name=f"{member.first_name} {member.last_name}",
                    uhid=a.uhid,
                    created_at=a.created_at,
                ).model_dump(mode="json")
            )
        return out

    async def _detail_hba1c_history(self, member_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(HealthRecord)
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_type.in_(
                    [RecordType.BLOOD_GLUCOSE, RecordType.DOCTOR_VISIT, RecordType.LAB_REPORT]
                ),
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
            .where(
                AIInsight.prompt == f"__drug_interactions__{member_id}",
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
                    return interactions
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    async def _detail_latest_insight(self, member_id: UUID) -> dict | None:
        # Scope to THIS member: an insight linked to one of the member's records
        # or one of the member's conversations. Without this the query returned
        # the global latest insight across every household (a cross-tenant leak
        # on the member-detail page).
        member_record_ids = select(HealthRecord.id).where(
            HealthRecord.family_member_id == member_id
        )
        member_conv_ids = select(Conversation.id).where(Conversation.family_member_id == member_id)
        result = await self.db.execute(
            select(AIInsight)
            .where(
                AIInsight.prompt.notlike("__drug_interactions__%"),
                AIInsight.prompt.notlike("__preconsult__%"),
                AIInsight.prompt.notlike("__smartreport__%"),
                or_(
                    AIInsight.health_record_id.in_(member_record_ids),
                    AIInsight.conversation_id.in_(member_conv_ids),
                ),
            )
            .order_by(AIInsight.generated_at.desc())
            .limit(1)
        )
        insight = result.scalar_one_or_none()
        if not insight:
            return None
        return serialize_insight_payload(insight)

    async def _detail_latest_preconsult(self, member_id: UUID) -> dict | None:
        result = await self.db.execute(
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
            return None
        return serialize_insight_payload(insight)

    async def _detail_latest_smart_report(self, member_id: UUID) -> dict | None:
        result = await self.db.execute(
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
            return None
        return serialize_smart_report_payload(insight)

    async def _detail_upcoming_reminders(self, member_id: UUID) -> list[dict]:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Reminder)
            .where(
                Reminder.family_member_id == member_id,
                Reminder.is_active.is_(True),
                Reminder.start_datetime >= now,
            )
            .order_by(Reminder.start_datetime.asc())
            .limit(10)
        )
        return [
            {
                "id": str(r.id),
                "title": r.title,
                "description": r.description,
                "start_datetime": r.start_datetime.isoformat() if r.start_datetime else None,
                "reminder_type": r.reminder_type.value
                if hasattr(r.reminder_type, "value")
                else r.reminder_type,
            }
            for r in result.scalars().all()
        ]

    async def _detail_vaccinations(self, member_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(Vaccination)
            .where(Vaccination.family_member_id == member_id)
            .order_by(Vaccination.date_administered.desc())
        )
        return [
            {
                "id": str(v.id),
                "name": v.name,
                "date_administered": v.date_administered.isoformat()
                if v.date_administered
                else None,
                "booster_due_date": v.booster_due_date.isoformat() if v.booster_due_date else None,
                "notes": v.notes,
            }
            for v in result.scalars().all()
        ]
