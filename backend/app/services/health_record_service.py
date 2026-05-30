"""Health record service."""
from pathlib import Path
from datetime import date, datetime, timedelta, time, timezone
from uuid import UUID
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import base64
import json
from app.core.database import update_model
from app.models.base import HealthRecord, RecordType


class HealthRecordService:
    """Health record management service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def create_record(
        self,
        member_id: UUID,
        record_type: RecordType,
        record_date: date,
        clinical_data: str,
        provider_id: UUID | None = None,
        record_time: time | None = None,
        diagnosis: str | None = None,
        prescription_text: str | None = None,
        next_review_date: date | None = None,
        tags: str | None = None,
    ) -> HealthRecord:
        """Create a new health record. Rejects exact duplicates within 2 minutes."""

        # Check for duplicate: same member, type, date, created within 2 min
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=2)
        existing = await self.db.execute(
            select(HealthRecord).where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_date == record_date,
                HealthRecord.record_type == record_type,
                HealthRecord.is_deleted.is_(False),
                HealthRecord.created_at >= cutoff,
            ).limit(1)
        )
        dup = existing.scalar_one_or_none()
        if dup and dup.clinical_data == clinical_data:
            raise ValueError("Duplicate record: an identical record was just created")

        record = HealthRecord(
            family_member_id=member_id,
            record_type=record_type,
            record_date=record_date,
            record_time=record_time,
            clinical_data=clinical_data,
            provider_id=provider_id,
            diagnosis=diagnosis,
            prescription_text=prescription_text,
            next_review_date=next_review_date,
            tags=tags,
        )
        self.db.add(record)
        await self.db.flush()
        # Refresh with provider and attachments eagerly loaded for response serialization
        await self.db.refresh(record, ["provider", "attachments"])
        return record
    async def get_record(self, member_id: UUID, record_id: UUID) -> HealthRecord:
        """Get record by ID, ensuring member access."""
        result = await self.db.execute(
            select(HealthRecord).options(
                joinedload(HealthRecord.provider),
                joinedload(HealthRecord.attachments),
            ).where(
                HealthRecord.id == record_id,
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
        )
        record = result.unique().scalar_one_or_none()
        if not record:
            raise ValueError("Record not found")
        return record

    async def list_records(
        self,
        member_id: UUID,
        record_type: RecordType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        cursor: dict | None = None,
        limit: int = 20,
    ) -> tuple[list[HealthRecord], str | None, bool]:
        """List records with optional filters and pagination."""
        query = select(HealthRecord).options(
            joinedload(HealthRecord.provider),
            joinedload(HealthRecord.attachments),
        ).where(
            HealthRecord.family_member_id == member_id,
            HealthRecord.is_deleted.is_(False),
        )

        if record_type:
            query = query.where(HealthRecord.record_type == record_type)
        if date_from:
            query = query.where(HealthRecord.record_date >= date_from)
        if date_to:
            query = query.where(HealthRecord.record_date <= date_to)
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(HealthRecord.clinical_data.ilike(f"%{escaped}%", escape="\\"))

        if cursor:
            query = query.where(
                tuple_(HealthRecord.record_date, HealthRecord.id)
                < (cursor["record_date"], cursor["id"])
            )

        query = query.order_by(
            HealthRecord.record_date.desc(), HealthRecord.id.desc()
        ).limit(limit + 1)

        result = await self.db.execute(query)
        records = list(result.scalars().unique().all())

        has_more = len(records) > limit
        items = records[:limit]
        next_cursor = (
            base64.b64encode(
                json.dumps({"record_date": str(items[-1].record_date), "id": str(items[-1].id)}).encode()
            ).decode()
            if has_more and items
            else None
        )

        return items, next_cursor, has_more

    async def update_record(self, record_id: UUID, **kwargs) -> HealthRecord:
        """Update record fields."""
        allowed = {
            "clinical_data", "diagnosis", "prescription_text",
            "next_review_date", "tags", "record_date", "record_time",
            "record_type", "provider_id",
        }
        result = await self.db.execute(
            select(HealthRecord)
            .options(joinedload(HealthRecord.provider), joinedload(HealthRecord.attachments))
            .where(HealthRecord.id == record_id)
        )
        record = result.unique().scalar_one()
        return await update_model(self.db, record, allowed_fields=allowed, **kwargs)

    async def soft_delete_record(self, member_id: UUID, record_id: UUID) -> None:
        """Soft-delete a health record and clean up associated attachment files."""
        record = await self.get_record(member_id, record_id)

        # Delete physical files for all attachments
        from app.core.storage import delete_file
        for attachment in record.attachments:
            try:
                await delete_file(Path(attachment.file_path))
            except Exception:
                pass  # File may already be gone

        record.is_deleted = True
        await self.db.flush()

    def _is_empty_clinical_data(self, clinical_data: str) -> bool:
        """Check if clinical_data has no meaningful content."""
        if not clinical_data or not clinical_data.strip():
            return True
        try:
            parsed = json.loads(clinical_data)
            if not isinstance(parsed, dict):
                return False
            if parsed.get("_type") != "structured":
                return False
            # Structured data: check if only metadata keys remain
            metadata_keys = {"_type", "_version", "_recordType", "_notes"}
            data_keys = [k for k in parsed if k not in metadata_keys]
            if not data_keys:
                return True
            # Check if all data values are empty
            for key in data_keys:
                val = parsed[key]
                if isinstance(val, list) and len(val) > 0:
                    # Non-empty table rows = has data
                    return False
                if isinstance(val, str) and val.strip():
                    return False
                if isinstance(val, (int, float)) and val != 0:
                    return False
                if isinstance(val, dict) and any(v for v in val.values() if v):
                    return False
            # All data keys present but values are empty
            return True
        except (json.JSONDecodeError, ValueError):
            # Plain text — non-empty means valid
            return not clinical_data.strip()

    async def find_empty_records(self, member_id: UUID) -> list[UUID]:
        """Find records with no meaningful data for a member."""

        result = await self.db.execute(
            select(HealthRecord)
            .options(joinedload(HealthRecord.attachments))
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
            )
        )
        records = result.unique().scalars().all()

        empty_ids: list[UUID] = []
        for record in records:
            has_attachments = bool(record.attachments)
            if has_attachments:
                continue
            if record.diagnosis and record.diagnosis.strip():
                continue
            if record.prescription_text and record.prescription_text.strip():
                continue
            if not self._is_empty_clinical_data(record.clinical_data):
                continue
            empty_ids.append(record.id)
        return empty_ids

    async def bulk_soft_delete(self, record_ids: list[UUID]) -> int:
        """Bulk soft-delete records by IDs. Returns count deleted."""
        if not record_ids:
            return 0
        result = await self.db.execute(
            select(HealthRecord).where(
                HealthRecord.id.in_(record_ids),
                HealthRecord.is_deleted.is_(False),
            )
        )
        records = result.scalars().all()
        for record in records:
            record.is_deleted = True
        await self.db.flush()
        return len(records)

    async def get_timeline(
        self,
        member_id: UUID,
        record_type: RecordType | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        cursor: dict | None = None,
        limit: int = 20,
    ) -> tuple[list[HealthRecord], str | None, bool]:
        """Get chronological timeline of records."""
        return await self.list_records(
            member_id, record_type, date_from, date_to, None, cursor, limit
        )

    async def get_lab_records_view(
        self, member_id: UUID, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """Get lab records in list view format.

        Includes standalone lab_report/blood_glucose records AND doctor_visit
        records that contain lab results in their structured clinical_data.
        """
        import json as _json

        lab_types = [RecordType.LAB_REPORT, RecordType.BLOOD_GLUCOSE]
        result = await self.db.execute(
            select(HealthRecord).options(joinedload(HealthRecord.provider))
            .where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.record_type.in_(lab_types + [RecordType.DOCTOR_VISIT]),
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
            .limit(limit)
            .offset(offset)
        )
        records = result.scalars().unique().all()

        def _get_tests(parsed: dict) -> list[dict]:
            """Extract test rows from either 'tests' or 'lab_results' key."""
            return parsed.get("lab_results") or parsed.get("tests") or []

        def _has_lab_data(clinical_data: str | None, record_type: str) -> bool:
            """Check if a record contains lab test data."""
            if record_type in ("lab_report", "blood_glucose"):
                return True
            if not clinical_data:
                return False
            try:
                parsed = _json.loads(clinical_data)
                if parsed.get("_type") == "structured":
                    return bool(_get_tests(parsed))
            except (ValueError, KeyError):
                pass
            return False

        def _extract_test_name(clinical_data: str | None) -> str:
            if not clinical_data:
                return "Unknown"
            try:
                parsed = _json.loads(clinical_data)
                if parsed.get("_type") == "structured":
                    if "glucose_value" in parsed:
                        return f"Glucose: {parsed['glucose_value']} mg/dL"
                    tests = _get_tests(parsed)
                    if tests:
                        names = [t.get("test_name", "") for t in tests if t.get("test_name")]
                        return ", ".join(names) if names else "Lab Report"
            except (ValueError, KeyError):
                pass
            return clinical_data[:50]

        def _extract_result(clinical_data: str | None) -> str:
            if not clinical_data:
                return ""
            try:
                parsed = _json.loads(clinical_data)
                if parsed.get("_type") == "structured":
                    if "glucose_value" in parsed:
                        return f"{parsed['glucose_value']} mg/dL ({parsed.get('meal_timing', '')})"
                    tests = _get_tests(parsed)
                    results = []
                    for t in tests:
                        r = t.get("result", "")
                        if r:
                            results.append(f"{t.get('test_name', '')}: {r}")
                    return "; ".join(results[:3])
            except (ValueError, KeyError):
                pass
            return ""

        return [
            {
                "id": r.id,
                "record_type": r.record_type,
                "record_date": r.record_date,
                "test_name": _extract_test_name(r.clinical_data),
                "result": _extract_result(r.clinical_data),
                "provider_name": r.provider.name if r.provider else None,
                "doctor_name": None,
            }
            for r in records
            if _has_lab_data(r.clinical_data, r.record_type)
        ]

