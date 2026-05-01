"""Medication expiry / refill tracking service."""
import json
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.models.base import HealthRecord, RecordType
from app.core.parsing import parse_duration

MEDICATION_SYNC_KEY = "_medication_sync"


class MedicationService:
    """Track medication prescriptions, expiry, and refill reminders."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_medications(self, member_id: UUID) -> list[dict]:
        """Get currently active medications for a member.

        Looks at the most recent doctor_visit records with structured
        clinical_data containing a 'prescriptions' array.  Each prescription
        has: medicine, type, dosage, duration, timing, note.

        Returns list of dicts with:
            medicine, type, dosage, timing, start_date, end_date, status
        Status is 'active' if end_date is in the future, 'completed' otherwise.
        end_date is computed from record_date + parsed duration.
        """
        result = await self.db.execute(
            select(HealthRecord)
            .options(load_only(HealthRecord.id, HealthRecord.record_date, HealthRecord.clinical_data))
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_type == RecordType.DOCTOR_VISIT,
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        )
        records = result.scalars().all()

        today = date.today()
        medications: list[dict] = []
        seen: set[str] = set()

        for r in records:
            if not r.clinical_data:
                continue

            parsed = self._parse_clinical_data(r.clinical_data)

            # Skip records where user chose "Save Only" (no medication sync)
            if parsed and parsed.get(MEDICATION_SYNC_KEY) is False:
                continue
            if not parsed or parsed.get("_type") != "structured":
                continue

            prescriptions = parsed.get("prescriptions", [])
            if not isinstance(prescriptions, list):
                continue

            for i, rx in enumerate(prescriptions):
                medicine = rx.get("medicine", "").strip()
                if not medicine:
                    continue

                # Deduplicate: keep only the latest prescription per medicine
                # (records are ordered by record_date DESC, so first = latest)
                key = medicine.strip().lower()
                if not key:
                    continue
                if key in seen:
                    continue
                seen.add(key)

                duration_days = parse_duration(rx.get("duration"))
                start_date = r.record_date
                end_date = start_date + timedelta(days=duration_days)

                status = "active" if end_date >= today else "completed"

                medications.append({
                    "medicine": medicine,
                    "type": rx.get("type", ""),
                    "dosage": rx.get("dosage", ""),
                    "timing": rx.get("timing", ""),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "duration": rx.get("duration", ""),
                    "note": rx.get("note", ""),
                    "status": status,
                    "record_id": str(r.id),
                    "prescription_index": i,
                    "provider_name": parsed.get("_provider_name"),
                })

        return medications

    async def get_refill_reminders(self, member_id: UUID) -> list[dict]:
        """Get medications that need refill within 7 days.

        Returns active medications whose end_date falls within the next 7 days
        (inclusive of today).
        """
        active_meds = await self.get_active_medications(member_id)

        today = date.today()
        cutoff = today + timedelta(days=7)

        reminders: list[dict] = []
        for med in active_meds:
            if med["status"] != "active":
                continue
            end = date.fromisoformat(med["end_date"])
            if today <= end <= cutoff:
                med["days_until_end"] = (end - today).days
                reminders.append(med)

        # Sort by days until end (soonest first)
        reminders.sort(key=lambda m: m["days_until_end"])
        return reminders

    async def remove_outdated_prescriptions(
        self, member_id: UUID, medicine_names: list[str]
    ) -> int:
        """Remove older prescriptions for the given medicine names across all records.

        Keeps only the most-recent prescription per medicine (by record_date).
        Returns the number of prescriptions removed.
        """
        if not medicine_names:
            return 0

        lookup = {self._normalize_medicine_name(name) for name in medicine_names if name.strip()}
        lookup.discard("")
        if not lookup:
            return 0

        result = await self.db.execute(
            select(HealthRecord)
            .options(load_only(HealthRecord.id, HealthRecord.record_date, HealthRecord.clinical_data))
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_type == RecordType.DOCTOR_VISIT,
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc(), HealthRecord.created_at.desc())
        )
        records = result.scalars().all()

        # Track which medicines we've already seen (newest record first)
        kept: set[str] = set()
        removed = 0

        for r in records:
            if not r.clinical_data:
                continue
            parsed = self._parse_clinical_data(r.clinical_data)
            if not parsed or parsed.get("_type") != "structured":
                continue

            prescriptions = parsed.get("prescriptions", [])
            if not isinstance(prescriptions, list):
                continue

            changed = False
            new_prescriptions: list[dict] = []
            for rx in prescriptions:
                med_name = rx.get("medicine", "").strip()
                key = self._normalize_medicine_name(med_name)
                if key in lookup:
                    if key not in kept:
                        # First (newest) occurrence — keep it
                        kept.add(key)
                        new_prescriptions.append(rx)
                    else:
                        # Older duplicate — remove
                        changed = True
                        removed += 1
                else:
                    new_prescriptions.append(rx)

            if changed:
                parsed["prescriptions"] = new_prescriptions
                r.clinical_data = json.dumps(parsed)
                if not new_prescriptions:
                    r.is_deleted = True

        if removed:
            await self.db.flush()
        return removed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_medicine_name(name: str) -> str:
        """Normalize medicine name for comparison.

        Takes the first word (actual drug name), lowercases it.
        E.g. "Metformin 500mg" -> "metformin"
        """
        return name.strip().lower().split()[0] if name.strip() else ""

    async def compute_medication_diff(
        self, member_id: UUID, new_prescriptions: list[dict]
    ) -> dict:
        """Compare new prescriptions against current active medications.

        Returns a dict with keys: added, updated, removed, unchanged.
        Each item contains: medicine, type, old_*/new_* fields, provider_name.
        """
        current_meds = await self.get_active_medications(member_id)

        # Build lookup of current meds by normalized name
        current_by_name: dict[str, dict] = {}
        for med in current_meds:
            key = self._normalize_medicine_name(med["medicine"])
            if key:
                current_by_name[key] = med

        added: list[dict] = []
        updated: list[dict] = []
        unchanged: list[dict] = []
        new_seen: set[str] = set()

        for rx in new_prescriptions:
            medicine = rx.get("medicine", "").strip()
            if not medicine:
                continue

            key = self._normalize_medicine_name(medicine)
            new_seen.add(key)

            diff_item = {
                "medicine": medicine,
                "type": rx.get("type", ""),
                "old_dosage": None,
                "new_dosage": rx.get("dosage", ""),
                "old_timing": None,
                "new_timing": rx.get("timing", ""),
                "old_duration": None,
                "new_duration": rx.get("duration", ""),
                "provider_name": None,
            }

            if key in current_by_name:
                current = current_by_name[key]
                diff_item["old_dosage"] = current.get("dosage", "")
                diff_item["old_timing"] = current.get("timing", "")
                diff_item["old_duration"] = current.get("duration", "")
                diff_item["provider_name"] = current.get("provider_name")

                # Check if anything changed
                if (
                    current.get("dosage", "") != rx.get("dosage", "")
                    or current.get("timing", "") != rx.get("timing", "")
                    or current.get("duration", "") != rx.get("duration", "")
                ):
                    updated.append(diff_item)
                else:
                    unchanged.append(diff_item)
            else:
                added.append(diff_item)

        # Find removed: current meds not in new prescriptions
        removed: list[dict] = []
        for key, med in current_by_name.items():
            if key not in new_seen:
                removed.append({
                    "medicine": med["medicine"],
                    "type": med.get("type", ""),
                    "old_dosage": med.get("dosage", ""),
                    "new_dosage": None,
                    "old_timing": med.get("timing", ""),
                    "new_timing": None,
                    "old_duration": med.get("duration", ""),
                    "new_duration": None,
                    "provider_name": med.get("provider_name"),
                })

        return {
            "added": added,
            "updated": updated,
            "removed": removed,
            "unchanged": unchanged,
        }

    async def apply_medication_changes(
        self,
        member_id: UUID,
        apply_added: list[str],
        apply_updated: list[str],
        apply_removed: list[str],
    ) -> dict:
        """Apply confirmed medication changes.

        Returns counts of changes applied. Added meds come from the new record
        (already saved), so they are acknowledged but not re-inserted here.
        """
        # For updated and removed, use remove_outdated_prescriptions
        # which keeps only the latest prescription per medicine.
        all_to_update = [
            name for name in apply_updated + apply_removed if name.strip()
        ]
        updated_removed = 0
        if all_to_update:
            updated_removed = await self.remove_outdated_prescriptions(member_id, all_to_update)

        return {
            "added": len(apply_added),
            "updated_or_removed": updated_removed,
        }

    @staticmethod
    def _parse_clinical_data(clinical_data: str | None) -> dict | None:
        """Safely parse clinical_data JSON string."""
        if not clinical_data:
            return None
        try:
            parsed = json.loads(clinical_data)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return None
