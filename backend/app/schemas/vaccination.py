"""Vaccination schemas."""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, date
from uuid import UUID


class VaccinationCreate(BaseModel):
    """Vaccination creation request."""

    name: str = Field(..., min_length=1, max_length=200, description="Vaccine name")
    date_administered: date = Field(..., description="Date administered")
    booster_due_date: date | None = Field(None, description="Next booster due date")
    notes: str | None = Field(None, description="Additional notes")


class VaccinationUpdate(BaseModel):
    """Vaccination update request."""

    name: str | None = Field(None, min_length=1, max_length=200, description="Vaccine name")
    date_administered: date | None = Field(None, description="Date administered")
    booster_due_date: date | None = Field(None, description="Next booster due date")
    notes: str | None = Field(None, description="Additional notes")


class VaccinationResponse(BaseModel):
    """Vaccination response."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Vaccination ID")
    family_member_id: UUID = Field(..., description="Family member ID")
    name: str = Field(..., description="Vaccine name")
    date_administered: date = Field(..., description="Date administered")
    booster_due_date: date | None = Field(None, description="Next booster due date")
    notes: str | None = Field(None, description="Additional notes")
    created_at: datetime = Field(..., description="Creation timestamp")
