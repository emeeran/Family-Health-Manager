"""Household schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class HouseholdCreate(BaseModel):
    """Household creation request."""

    name: str = Field(..., min_length=1, max_length=100, description="Household name")


class HouseholdUpdate(BaseModel):
    """Household update request."""

    name: str | None = Field(None, min_length=1, max_length=100, description="Household name")


class HouseholdResponse(BaseModel):
    """Household response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Household ID")
    name: str = Field(..., description="Household name")
    primary_user_id: UUID = Field(..., description="Primary user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
