"""Provider schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class ProviderCreate(BaseModel):
    """Provider creation request."""

    name: str = Field(..., min_length=1, max_length=100, description="Provider name")
    provider_type: str = Field("doctor", max_length=20, description="Provider type")
    speciality: str | None = Field(None, min_length=1, max_length=100, description="Speciality")
    phone: str | None = Field(None, min_length=1, max_length=20, description="Phone number")
    address: str | None = Field(None, description="Clinic/hospital address")


class ProviderUpdate(BaseModel):
    """Provider update request."""

    name: str | None = Field(None, min_length=1, max_length=100, description="Provider name")
    provider_type: str | None = Field(None, max_length=20, description="Provider type")
    speciality: str | None = Field(None, min_length=1, max_length=100, description="Speciality")
    phone: str | None = Field(None, min_length=1, max_length=20, description="Phone number")
    address: str | None = Field(None, description="Clinic/hospital address")


class AssignedMember(BaseModel):
    """Short summary of a member assigned to a provider."""

    family_member_id: UUID
    family_member_name: str
    uhid: str | None = None
    visit_count: int = 0


class ProviderResponse(BaseModel):
    """Provider response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Provider ID")
    household_id: UUID = Field(..., description="Household ID")
    name: str = Field(..., description="Provider name")
    provider_type: str = Field("doctor", description="Provider type")
    speciality: str | None = Field(None, description="Speciality")
    phone: str | None = Field(None, description="Phone number")
    address: str | None = Field(None, description="Clinic/hospital address")
    created_at: datetime = Field(..., description="Creation timestamp")
    assigned_members: list[AssignedMember] = Field(default_factory=list, description="Assigned family members")
