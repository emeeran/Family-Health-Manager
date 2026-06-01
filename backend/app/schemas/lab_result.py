"""Lab result schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, date
from uuid import UUID


class LabResultResponse(BaseModel):
    """Lab result response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Lab result ID")
    family_member_id: UUID = Field(..., description="Family member ID")
    health_record_id: UUID | None = Field(None, description="Source health record ID")
    test_name: str = Field(..., description="Test name")
    result: str = Field(..., description="Test result value")
    units: str = Field("", description="Result units")
    ref_value: str = Field("", description="Reference range")
    note: str = Field("", description="Additional notes")
    record_date: date | None = Field(None, description="Date of the test")
    created_at: datetime = Field(..., description="Creation timestamp")
