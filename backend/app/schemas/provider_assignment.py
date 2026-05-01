"""Provider assignment schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class ProviderAssignmentCreate(BaseModel):
    """Provider assignment creation request."""

    provider_id: UUID = Field(..., description="Provider ID")
    uhid: str | None = Field(None, min_length=1, max_length=50, description="Unique Health ID")


class ProviderAssignmentResponse(BaseModel):
    """Provider assignment response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Assignment ID")
    provider_id: UUID = Field(..., description="Provider ID")
    provider_name: str = Field(..., description="Provider name")
    family_member_id: UUID = Field(..., description="Family member ID")
    family_member_name: str = Field(..., description="Family member name")
    uhid: str | None = Field(None, description="Unique Health ID")
    created_at: datetime = Field(..., description="Creation timestamp")
