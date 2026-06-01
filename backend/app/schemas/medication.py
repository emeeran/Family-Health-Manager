"""Medication schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, date
from uuid import UUID


class MedicationCreate(BaseModel):
    """Medication creation request."""

    medicine: str = Field(..., min_length=1, description="Medicine name")
    type: str = Field("", description="Form: Tab/Cap/Inj/Syp/etc")
    dosage: str = Field("", description="Dosage amount")
    timing: str = Field("", description="Before/after food etc")
    duration: str = Field("", description="Duration text")
    note: str = Field("", description="Additional notes")


class MedicationResponse(BaseModel):
    """Medication response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Medication ID")
    family_member_id: UUID = Field(..., description="Family member ID")
    health_record_id: UUID | None = Field(None, description="Source health record ID")
    medicine: str = Field(..., description="Medicine name")
    medicine_key: str = Field(..., description="Normalized medicine key")
    type: str = Field("", description="Form: Tab/Cap/Inj/Syp/etc")
    dosage: str = Field("", description="Dosage amount")
    timing: str = Field("", description="Before/after food etc")
    duration: str = Field("", description="Duration text")
    duration_days: int = Field(30, description="Duration in days")
    note: str = Field("", description="Additional notes")
    start_date: date | None = Field(None, description="Start date")
    end_date: date | None = Field(None, description="End date")
    status: str = Field("active", description="Status: active/completed/discontinued/superseded")
    prescription_index: int = Field(0, description="Position in prescriptions array")
    provider_name: str = Field("", description="Prescribing provider name")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
