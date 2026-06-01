"""Health record router."""
import asyncio
import logging
from datetime import date, datetime, time
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
from app.core.database import get_db
from app.core.deps import get_household_from_token, require_member_in_household, decode_cursor
from app.core.sse import make_sse_stream
from app.core.storage import validate_file, save_file
from app.services.health_record_service import HealthRecordService
from app.services.attachment_service import AttachmentService
from app.services.reminder_service import ReminderService
from app.services.ai_service import AIService
from app.core.cache import cache
from app.schemas.health_record import (
    HealthRecordCreate, HealthRecordUpdate, HealthRecordResponse,
    ExtractionResponse, ExtractedFields, TimelineResponse,
    BatchExtractionItemSchema, BatchExtractionResponse,
    CheckFilenamesRequest, CheckFilenamesResponse,
    BatchDeleteRequest,
)
from app.models.base import Household, FamilyMember, RecordType
from app.models.attachment import Attachment
from app.models.record import HealthRecord

router = APIRouter(prefix="/members/{member_id}/records", tags=["Health Records"])
logger = logging.getLogger(__name__)


@router.post("/extract", response_model=ExtractionResponse)
async def extract_from_document(
    member_id: UUID,
    file: UploadFile = File(...),
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Upload a medical document, extract data via AI, return structured fields."""
    from app.services.ai_service import AIService

    validate_file(file)
    file_path, unique_filename = await save_file(file, prefix="staging")

    ai_service = AIService(db)
    try:
        extracted = await ai_service.extract_medical_data(
            str(file_path), file.content_type or "application/octet-stream"
        )
        provider_used = ai_service.last_provider
    except Exception as exc:
        logger.error("AI extraction failed: %s", exc)
        extracted = ExtractedFields()
        provider_used = ""

    # Run extraction verification using a different AI provider
    verification = None
    try:
        from app.services.verification_service import VerificationService
        verification_svc = VerificationService(db, ai_service)
        verification = await verification_svc.verify_extraction(
            extracted.model_dump(),
            original_provider=provider_used,
        )
    except Exception as exc:
        logger.debug("Extraction verification skipped: %s", exc)

    return ExtractionResponse(
        staging_file_id=unique_filename,
        original_file_name=file.filename,
        extracted=extracted,
        confidence="low" if not extracted.has_any_data() else "medium",
        verification=verification,
    )


async def _extract_single_file(
    file: UploadFile, ai_service: AIService
) -> BatchExtractionItemSchema:
    """Extract a single file, returning a BatchExtractionItemSchema.

    Note: No DB access here — this runs inside asyncio.gather where the
    session must not be shared across concurrent coroutines. Verification
    runs separately after the batch completes (see extract_batch).
    """
    try:
        validate_file(file)
    except ValueError as exc:
        return BatchExtractionItemSchema(
            filename=file.filename or "unknown",
            error=str(exc),
        )

    try:
        file_path, unique_filename = await save_file(file, prefix="staging")
    except Exception as exc:
        return BatchExtractionItemSchema(
            filename=file.filename or "unknown",
            error=f"Failed to save file: {exc}",
        )

    try:
        extracted = await ai_service.extract_medical_data(
            str(file_path), file.content_type or "application/octet-stream"
        )

        return BatchExtractionItemSchema(
            filename=file.filename or "unknown",
            staging_file_id=unique_filename,
            extracted=extracted,
        )
    except Exception as exc:
        logger.error("AI extraction failed for %s: %s", file.filename, exc)
        return BatchExtractionItemSchema(
            filename=file.filename or "unknown",
            staging_file_id=unique_filename,
            extracted=ExtractedFields(),
            error=f"Extraction failed: {exc}",
        )


@router.post("/extract-batch", response_model=BatchExtractionResponse)
async def extract_batch(
    member_id: UUID,
    files: list[UploadFile] = File(...),
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Upload multiple medical documents and extract data via AI.

    Processes files in parallel batches of 3 to avoid overwhelming AI providers.
    """
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files per batch")

    # Note: AIService is shared across asyncio.gather coroutines.
    # This is safe because extraction only calls read-only AI provider methods
    # (no mutable state mutation). The _ollama_client lazy-init is the only
    # shared mutable field, but Ollama runs as a separate service now.
    ai_service = AIService(db)
    results: list[BatchExtractionItemSchema] = []
    batch_size = 3

    for i in range(0, len(files), batch_size):
        chunk = files[i : i + batch_size]
        chunk_results = await asyncio.gather(
            *[_extract_single_file(f, ai_service) for f in chunk]
        )
        results.extend(chunk_results)

    # Run verification in parallel for all successful extractions
    from app.services.verification_service import VerificationService
    verification_svc = VerificationService(db, ai_service)

    async def _verify_item(item: BatchExtractionItemSchema) -> None:
        if item.extracted and not item.error:
            try:
                item.verification = await verification_svc.verify_extraction(
                    item.extracted.model_dump(),
                    original_provider="",
                )
            except Exception as exc:
                logger.debug("Batch verification skipped for %s: %s", item.filename, exc)

    await asyncio.gather(*[_verify_item(item) for item in results])

    return BatchExtractionResponse(extractions=results)


@router.post("/check-filenames", response_model=CheckFilenamesResponse)
async def check_filenames(
    member_id: UUID,
    body: CheckFilenamesRequest,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Check which filenames already have associated records.

    Accepts: {"filenames": ["file1.pdf", "file2.jpg"]}
    Returns: {"existing": ["file1.pdf"]} with filenames that already have records.
    """
    filenames = body.filenames
    if not filenames:
        return CheckFilenamesResponse(existing=[])

    # Query attachment filenames scoped to THIS member's records
    result = await db.execute(
        select(Attachment.file_name)
        .join(Attachment.health_record)
        .where(
            Attachment.file_name.in_(filenames),
            HealthRecord.family_member_id == member_id,
            HealthRecord.is_deleted.is_(False),
        )
    )
    existing = [row[0] for row in result.all()]
    return CheckFilenamesResponse(existing=existing)


@router.get("", response_model=list[HealthRecordResponse])
async def list_records(
    member_id: UUID,
    response: Response,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
    record_type: RecordType | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, le=100),
):
    """List health records for a member."""
    record_service = HealthRecordService(db)
    cursor_dict = decode_cursor(cursor)
    records, next_cursor, has_more = await record_service.list_records(
        member_id, record_type, date_from, date_to, search, cursor_dict, limit
    )
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor
    return records



@router.post("", status_code=201, response_model=HealthRecordResponse)
async def create_record(
    member_id: UUID,
    request: HealthRecordCreate,
    staging_file_ids: str | None = Query(None, description="Comma-separated staging file IDs to attach"),
    original_file_names: str | None = Query(None, description="Comma-separated original file names (same order as staging_file_ids)"),
    household: Household = Depends(get_household_from_token),
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Create a health record, optionally attaching previously uploaded files."""

    record_service = HealthRecordService(db)
    tags_json = json.dumps(request.tags) if request.tags else None
    try:
        record = await record_service.create_record(
            member_id=member_id,
            record_type=request.record_type,
            record_date=request.record_date,
            clinical_data=request.clinical_data,
            provider_id=request.provider_id,
            record_time=request.record_time,
            diagnosis=request.diagnosis,
            prescription_text=request.prescription_text,
            next_review_date=request.next_review_date,
            tags=tags_json,
        )
    except ValueError as e:
        if "Duplicate" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise

    if staging_file_ids:
        attachment_service = AttachmentService(db)
        names = original_file_names.split(",") if original_file_names else []
        for i, fid in enumerate(staging_file_ids.split(",")):
            fid = fid.strip()
            if fid:
                try:
                    orig_name = names[i].strip() if i < len(names) else None
                    await attachment_service.attach_staged_file(record.id, fid, orig_name)
                except ValueError:
                    logger.warning("Staging file %s not found, skipping", fid)

    # Remove outdated prescriptions if this record has medications synced
    if (
        request.record_type == RecordType.DOCTOR_VISIT
        and request.clinical_data
    ):
        try:
            from app.services.medication_service import MedicationService
            parsed_cd = json.loads(request.clinical_data) if isinstance(request.clinical_data, str) else request.clinical_data
            if isinstance(parsed_cd, dict) and parsed_cd.get("_medication_sync") is not False:
                prescriptions = parsed_cd.get("prescriptions", [])
                if isinstance(prescriptions, list):
                    med_names = [
                        rx.get("medicine", "").strip()
                        for rx in prescriptions
                        if rx.get("medicine", "").strip()
                    ]
                    if med_names:
                        med_svc = MedicationService(db)
                        await med_svc.remove_outdated_prescriptions(member_id, med_names)
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Outdated prescription cleanup skipped: %s", exc)

    # Sync medications and lab results into first-class tables
    if request.clinical_data:
        try:
            from app.services.medication_service import MedicationService
            from app.services.lab_result_service import LabResultService
            provider_name_val = None
            if record.provider:
                provider_name_val = record.provider.name
            med_svc = MedicationService(db)
            await med_svc.sync_from_record(
                member_id, record.id, request.clinical_data,
                request.record_date, provider_name_val,
            )
            lab_svc = LabResultService(db)
            await lab_svc.sync_from_record(
                member_id, record.id, request.clinical_data,
                request.record_date,
            )
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Medication/lab sync skipped: %s", exc)

    # Fire-and-forget AI insight generation
    try:
        from app.services.insight_service import spawn_insight_task
        spawn_insight_task(record.id)
    except Exception:
        logger.debug("Insight generation skipped")

    # Invalidate cached member context so next insight uses fresh data
    AIService.invalidate_member_cache(member_id)

    # Auto-create FOLLOW_UP reminder if next_review_date is set (deduped)
    if record.next_review_date:
        try:
            reminder_svc = ReminderService(db)
            await reminder_svc.create_follow_up_if_not_exists(
                household_id=household.id,
                member_id=member_id,
                review_date=datetime.combine(record.next_review_date, time(9, 0)),
                title=f"Follow-up review — {record.next_review_date.strftime('%b %d, %Y')}",
                description=(
                    f"Scheduled review from health record "
                    f"({record.record_type.value}) created on {record.record_date.strftime('%b %d, %Y')}"
                ),
            )
        except Exception:
            logger.warning("Failed to create follow-up reminder for record %s", record.id)

    await cache.invalidate_async(f"household_records:{household.id}")
    await cache.invalidate_async(f"dashboard_summary:{household.id}")
    return record


@router.get("/timeline/list", response_model=TimelineResponse)
async def get_timeline(
    member_id: UUID,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
    record_type: RecordType | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, le=100),
):
    """Get chronological timeline of records."""
    record_service = HealthRecordService(db)
    cursor_dict = decode_cursor(cursor)

    records, next_cursor, has_more = await record_service.get_timeline(
        member_id, record_type, date_from, date_to, cursor_dict, limit
    )
    return {"items": records, "next_cursor": next_cursor, "has_more": has_more}


@router.get("/lab-records")
async def get_lab_records(
    member_id: UUID,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Get lab records list view."""
    record_service = HealthRecordService(db)
    lab_records = await record_service.get_lab_records_view(member_id)
    return {"items": lab_records}


@router.post("/cleanup")
async def cleanup_empty_records(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Find and soft-delete records with no meaningful data."""
    record_service = HealthRecordService(db)
    empty_ids = await record_service.find_empty_records(member_id)
    count = await record_service.bulk_soft_delete(empty_ids)
    if count:
        await cache.invalidate_async(f"household_records:{household.id}")
        await cache.invalidate_async(f"dashboard_summary:{household.id}")
        AIService.invalidate_member_cache(member_id)
    return {"removed": count}


@router.post("/batch-delete")
async def batch_delete_records(
    member_id: UUID,
    body: BatchDeleteRequest,
    household: Household = Depends(get_household_from_token),
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete multiple health records by IDs."""
    record_ids = [UUID(rid) for rid in body.record_ids]
    result = await db.execute(
        select(HealthRecord).where(
            HealthRecord.id.in_(record_ids),
            HealthRecord.family_member_id == member_id,
            HealthRecord.is_deleted.is_(False),
        )
    )
    records = result.scalars().all()
    for record in records:
        record.is_deleted = True
    await db.flush()
    count = len(records)
    if count:
        await cache.invalidate_async(f"household_records:{household.id}")
        await cache.invalidate_async(f"dashboard_summary:{household.id}")
        AIService.invalidate_member_cache(member_id)
    return {"deleted": count}


@router.get("/{record_id}", response_model=HealthRecordResponse)
async def get_record(
    member_id: UUID,
    record_id: UUID,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific health record."""
    record_service = HealthRecordService(db)
    try:
        record = await record_service.get_record(member_id, record_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@router.put("/{record_id}", response_model=HealthRecordResponse)
async def update_record(
    member_id: UUID,
    record_id: UUID,
    request: HealthRecordUpdate,
    household: Household = Depends(get_household_from_token),
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Update a health record."""
    record_service = HealthRecordService(db)

    try:
        await record_service.get_record(member_id, record_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Record not found")

    update_data = request.model_dump(exclude_unset=True)

    # Convert tags list to JSON string
    if "tags" in update_data:
        tags_list = update_data.pop("tags")
        update_data["tags"] = json.dumps(tags_list) if tags_list else None

    record = await record_service.update_record(record_id, **update_data)
    AIService.invalidate_member_cache(member_id)

    # Sync medications and lab results if clinical_data was updated
    if "clinical_data" in update_data and update_data.get("clinical_data"):
        try:
            from app.services.medication_service import MedicationService
            from app.services.lab_result_service import LabResultService
            provider_name_val = None
            if record.provider:
                provider_name_val = record.provider.name
            med_svc = MedicationService(db)
            await med_svc.sync_from_record(
                member_id, record.id, update_data["clinical_data"],
                record.record_date, provider_name_val,
            )
            lab_svc = LabResultService(db)
            await lab_svc.sync_from_record(
                member_id, record.id, update_data["clinical_data"],
                record.record_date,
            )
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Medication/lab sync on update skipped: %s", exc)

    # Auto-create FOLLOW_UP reminder if next_review_date was just set (deduped)
    if "next_review_date" in update_data and record.next_review_date:
        try:
            reminder_svc = ReminderService(db)
            await reminder_svc.create_follow_up_if_not_exists(
                household_id=household.id,
                member_id=member_id,
                review_date=datetime.combine(record.next_review_date, time(9, 0)),
                title=f"Follow-up review — {record.next_review_date.strftime('%b %d, %Y')}",
                description=(
                    f"Scheduled review from updated health record "
                    f"({record.record_type.value}) on {record.record_date.strftime('%b %d, %Y')}"
                ),
            )
        except Exception:
            logger.warning("Failed to create follow-up reminder on update for record %s", record_id)

    await cache.invalidate_async(f"household_records:{household.id}")
    await cache.invalidate_async(f"dashboard_summary:{household.id}")
    return record


@router.delete("/{record_id}", status_code=204)
async def delete_record(
    member_id: UUID,
    record_id: UUID,
    household: Household = Depends(get_household_from_token),
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a health record."""
    record_service = HealthRecordService(db)

    try:
        await record_service.soft_delete_record(member_id, record_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Record not found")
    await cache.invalidate_async(f"household_records:{household.id}")
    await cache.invalidate_async(f"dashboard_summary:{household.id}")
    AIService.invalidate_member_cache(member_id)


@router.get("/{record_id}/insight")
async def get_record_insight(
    member_id: UUID,
    record_id: UUID,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest AI-generated insight for a health record."""
    from sqlalchemy import select
    from app.models.base import AIInsight

    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.health_record_id == record_id,
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        return {"insight": None}

    return {
        "insight": {
            "id": str(insight.id),
            "prompt": insight.prompt,
            "response": insight.response,
            "provider_used": insight.provider_used,
            "generated_at": insight.generated_at.isoformat(),
            "verification": _verification_dict(insight),
        },
    }


def _verification_dict(insight):
    """Build verification payload from an AIInsight record."""
    if insight.verification_status == "pending" and insight.verification_at is None:
        return {"status": "pending"}
    return {
        "status": insight.verification_status,
        "claims_checked": insight.verification_claims_checked,
        "verifier_provider": insight.verification_verifier,
        "summary": insight.verification_summary,
        "warnings": json.loads(insight.verification_warnings_json) if insight.verification_warnings_json else None,
        "verified_at": insight.verification_at.isoformat() if insight.verification_at else None,
    }


@router.get("/{record_id}/insight/verification")
async def get_insight_verification(
    member_id: UUID,
    record_id: UUID,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Poll for insight verification result."""
    from sqlalchemy import select
    from app.models.base import AIInsight

    result = await db.execute(
        select(AIInsight)
        .where(AIInsight.health_record_id == record_id)
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(status_code=404, detail="No insight found")

    return _verification_dict(insight)


@router.post("/{record_id}/regenerate-insight")
async def regenerate_record_insight(
    member_id: UUID,
    record_id: UUID,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate the AI insight for a health record."""
    from app.services.insight_service import InsightService

    record_service = HealthRecordService(db)
    try:
        await record_service.get_record(member_id, record_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Record not found")

    insight_svc = InsightService(db)
    insight = await insight_svc.generate_record_insight(record_id)

    if not insight:
        raise HTTPException(status_code=502, detail="AI service unavailable. Please try again.")

    return {
        "insight": {
            "id": str(insight.id),
            "prompt": insight.prompt,
            "response": insight.response,
            "provider_used": insight.provider_used,
            "generated_at": insight.generated_at.isoformat(),
            "verification": _verification_dict(insight),
        },
    }


@router.post("/{record_id}/regenerate-insight/stream")
async def regenerate_record_insight_stream(
    member_id: UUID,
    record_id: UUID,
    _member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Stream AI insight generation with real-time progress (SSE)."""
    from app.services.ai_service import AIService
    from app.services.insight_service import InsightService

    record_service = HealthRecordService(db)
    try:
        record = await record_service.get_record(member_id, record_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Record not found")

    insight_svc = InsightService(db)
    prompt = insight_svc._build_prompt(record)

    ai_service = AIService(db)

    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            health_record_id=record_id,
            member_id=record.family_member_id,
            comprehensive=True,
        ),
        db,
    )
