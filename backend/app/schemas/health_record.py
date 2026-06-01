"""Health record schemas."""
import json
from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime, date, time
from uuid import UUID
from app.models.base import RecordType
from app.schemas.attachment import AttachmentResponse


class HealthRecordCreate(BaseModel):
    """Health record creation request."""

    provider_id: UUID | None = Field(None, description="Provider ID")
    record_type: RecordType = Field(..., description="Type of health record")
    record_date: date = Field(..., description="Date of record")
    record_time: time | None = Field(None, description="Time of record")
    clinical_data: str = Field(..., description="Clinical data", max_length=50000)
    diagnosis: str | None = Field(None, description="Diagnosis")
    prescription_text: str | None = Field(None, description="Prescription notes")
    next_review_date: date | None = Field(None, description="Next review date")
    tags: list[str] | None = Field(None, description="Record tags")


class HealthRecordUpdate(BaseModel):
    """Health record update request."""

    provider_id: UUID | None = Field(None, description="Provider ID")
    clinical_data: str | None = Field(None, description="Clinical data", max_length=50000)
    diagnosis: str | None = Field(None, description="Diagnosis")
    prescription_text: str | None = Field(None, description="Prescription notes")
    next_review_date: date | None = Field(None, description="Next review date")
    tags: list[str] | None = Field(None, description="Record tags")


class HealthRecordResponse(BaseModel):
    """Health record response."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: UUID = Field(..., description="Health record ID")
    family_member_id: UUID = Field(..., description="Family member ID")
    provider_id: UUID | None = Field(None, description="Provider ID")
    provider_name: str | None = Field(None, description="Provider name")
    record_type: RecordType = Field(..., description="Record type")
    record_date: date = Field(..., description="Record date")
    record_time: time | None = Field(None, description="Record time")
    clinical_data: str = Field(..., description="Clinical data", max_length=50000)
    diagnosis: str | None = Field(None, description="Diagnosis")
    prescription_text: str | None = Field(None, description="Prescription notes")
    next_review_date: date | None = Field(None, description="Next review date")
    is_deleted: bool = Field(..., description="Soft-delete flag")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    attachments: list[AttachmentResponse] = Field(default_factory=list, description="File attachments")

    # Parsed once from the raw tags column (JSON text → list[str])
    tags: list[str] | None = Field(None, description="Record tags")

    @model_validator(mode="before")
    @classmethod
    def _parse_tags(cls, data):
        """Parse tags JSON column once during construction."""
        if isinstance(data, dict):
            raw = data.get("tags")
            if isinstance(raw, str):
                try:
                    items = json.loads(raw)
                    if isinstance(items, list) and len(items) > 0:
                        data["tags"] = items
                    else:
                        data["tags"] = None
                except (json.JSONDecodeError, ValueError):
                    data["tags"] = None
        return data


class ExtractedFields(BaseModel):
    """AI-extracted health record fields."""

    record_type: RecordType | None = Field(None, description="Detected record type")
    record_date: date | None = Field(None, description="Date found in document")
    record_time: time | None = Field(None, description="Time found in document")
    clinical_data: str | None = Field(None, description="Extracted clinical data/notes", max_length=50000)
    diagnosis: str | None = Field(None, description="Extracted diagnosis")
    existing_conditions: str | None = Field(None, description="Existing/chronic conditions found")
    chief_complaint: str | None = Field(None, description="Chief complaint / reason for visit")
    investigations: str | None = Field(None, description="Investigations ordered or recommended")
    prescription_text: str | None = Field(None, description="Extracted prescription (text fallback)")
    provider_name: str | None = Field(None, description="Provider name found")
    next_review_date: date | None = Field(None, description="Next review/follow-up date")
    prescriptions: list[dict] | None = Field(None, description="Structured prescription rows")
    lab_tests: list[dict] | None = Field(None, description="Structured lab test rows")
    eyeglass: dict | None = Field(None, description="Structured eyeglass prescription")

    def has_any_data(self) -> bool:
        """Check if at least one field has data."""
        return bool(
            self.record_type
            or self.record_date
            or self.clinical_data
            or self.diagnosis
            or self.existing_conditions
            or self.chief_complaint
            or self.investigations
            or self.prescription_text
            or self.provider_name
            or self.next_review_date
            or self.prescriptions
            or self.lab_tests
            or self.eyeglass
        )


class ExtractionResponse(BaseModel):
    """Response from document extraction endpoint."""

    staging_file_id: str = Field(..., description="Temporary staging file reference")
    original_file_name: str | None = Field(None, description="Original uploaded file name")
    extracted: ExtractedFields = Field(..., description="AI-extracted fields")
    confidence: str = Field("medium", description="Extraction confidence: high/medium/low")
    verification: dict | None = Field(None, description="Cross-verification result (if available)")


class TimelineResponse(BaseModel):
    """Timeline endpoint response."""

    items: list[HealthRecordResponse]
    next_cursor: str | None = None
    has_more: bool = False


class BatchExtractionItemSchema(BaseModel):
    """Single item in a batch extraction response."""

    filename: str = Field(..., description="Original file name")
    staging_file_id: str | None = Field(None, description="Staging file reference")
    extracted: ExtractedFields | None = Field(None, description="AI-extracted fields")
    is_duplicate: bool = Field(False, description="Whether this is a duplicate of an existing record")
    duplicate_of_id: str | None = Field(None, description="ID of the record this duplicates")
    duplicate_of_diagnosis: str | None = Field(None, description="Diagnosis of the duplicate record")
    error: str | None = Field(None, description="Error message if extraction failed")
    verification: dict | None = Field(None, description="Cross-verification result (if available)")


class BatchExtractionResponse(BaseModel):
    """Response from batch extraction endpoint."""

    extractions: list[BatchExtractionItemSchema] = Field(..., description="Extraction results per file")


class BatchDeleteRequest(BaseModel):
    """Request body for batch-delete endpoint."""

    record_ids: list[str] = Field(..., min_length=1, max_length=500, description="Record IDs to delete")


class CheckFilenamesRequest(BaseModel):
    """Request body for check-filenames endpoint."""

    filenames: list[str] = Field(..., max_length=500, description="Filenames to check")


class CheckFilenamesResponse(BaseModel):
    """Response from check-filenames endpoint."""

    existing: list[str] = Field(default_factory=list, description="Filenames that already have records")
