"""Household schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID


class FeatureSettings(BaseModel):
    """Feature toggle settings for a household."""

    ai_features: bool = True
    ai_verification: bool = True
    notifications: bool = True
    email_notifications: bool = False
    smart_entry: bool = True


class HouseholdSettingsResponse(BaseModel):
    """Response for household settings."""

    settings: FeatureSettings


class HouseholdSettingsUpdate(BaseModel):
    """Update request for household settings."""

    settings: FeatureSettings


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
    settings: FeatureSettings = Field(default_factory=FeatureSettings, description="Feature settings")
