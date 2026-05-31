"""Medication tracking router — active medications, refill reminders, and CRUD operations."""
import json
import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.base import Household, HealthRecord, RecordType
from app.services.medication_service import MedicationService
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members/{member_id}/medications", tags=["Medications"])


# --- Pydantic models for medication CRUD ---


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


# --- Helpers ---


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


async def _verify_member(household_id, member_id: UUID, db: AsyncSession):
    service = MemberService(db)
    try:
        return await service.get_member(household_id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")


# --- Read-only routes ---


@router.get("/active")
async def get_active_medications(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get currently active medications for a family member."""
    await _verify_member(household.id, member_id, db)

    medication_service = MedicationService(db)
    medications = await medication_service.get_active_medications(member_id)
    return {"items": medications}


@router.get("/refill-reminders")
async def get_refill_reminders(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get medications that need refill within the next 7 days."""
    await _verify_member(household.id, member_id, db)

    medication_service = MedicationService(db)
    reminders = await medication_service.get_refill_reminders(member_id)
    return {"items": reminders}


# --- CRUD routes ---


@router.post("", status_code=201)
async def add_medication(
    member_id: UUID,
    body: MedicationInput,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Add a single medication as a new doctor_visit record."""
    await _verify_member(household.id, member_id, db)

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

    med_svc = MedicationService(db)
    med_name = rx.get("medicine", "").strip()
    if med_name:
        await med_svc.remove_outdated_prescriptions(member_id, [med_name])

    await db.commit()
    await cache.invalidate_async(f"dashboard:{member_id}")
    return {
        "id": str(record.id),
        "prescription": rx,
        "record_id": str(record.id),
        "prescription_index": 0,
    }


@router.put("")
async def update_medication(
    member_id: UUID,
    body: MedicationUpdate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update a specific prescription within a health record."""
    await _verify_member(household.id, member_id, db)

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

    await cache.invalidate_async(f"dashboard:{member_id}")
    return {"updated": True}


@router.delete("")
async def delete_medication(
    member_id: UUID,
    body: MedicationDelete,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific prescription from a health record.
    If it was the only prescription, soft-delete the entire record."""
    await _verify_member(household.id, member_id, db)

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

        record.clinical_data = _rebuild_clinical_data(parsed, prescriptions)

        if len(prescriptions) == 0:
            record.is_deleted = True

        await db.flush()
    except (json.JSONDecodeError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Cannot edit unstructured record")

    await cache.invalidate_async(f"dashboard:{member_id}")
    return {"deleted": True}


@router.post("/bulk-delete")
async def bulk_delete_medications(
    member_id: UUID,
    body: MedicationBulkDelete,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple prescriptions across records in one request."""
    logger.info("bulk-delete: received %d items for member %s", len(body.items), member_id)
    for item in body.items:
        logger.info("bulk-delete: item record_id=%s prescription_index=%d", item.record_id, item.prescription_index)

    await _verify_member(household.id, member_id, db)

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

            record.clinical_data = _rebuild_clinical_data(parsed, prescriptions)

            if len(prescriptions) == 0:
                record.is_deleted = True

            await db.flush()
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            logger.exception("bulk-delete: failed to process record %s", record_id_str)
            continue

    await cache.invalidate_async(f"dashboard:{member_id}")
    return {"deleted": deleted}


@router.post("/diff")
async def compute_medication_diff(
    member_id: UUID,
    body: MedicationDiffRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Compute the diff between new prescriptions and current active medications."""
    await _verify_member(household.id, member_id, db)

    med_svc = MedicationService(db)
    diff = await med_svc.compute_medication_diff(member_id, body.prescriptions)
    return diff


@router.post("/apply-sync")
async def apply_medication_sync(
    member_id: UUID,
    body: MedicationApplyRequest,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Apply confirmed medication sync changes."""
    await _verify_member(household.id, member_id, db)

    med_svc = MedicationService(db)
    result = await med_svc.apply_medication_changes(
        member_id,
        apply_added=body.apply_added,
        apply_updated=body.apply_updated,
        apply_removed=body.apply_removed,
    )
    await db.commit()

    await cache.invalidate_async(f"dashboard:{member_id}")
    return result
