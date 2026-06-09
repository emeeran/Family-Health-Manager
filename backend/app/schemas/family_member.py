"""Family member schemas."""
import json
from pydantic import BaseModel, Field, ConfigDict, computed_field, model_validator
from datetime import datetime, date
from uuid import UUID
from app.models.base import Gender, Relationship


class AllergyEntry(BaseModel):
    """Single allergy with severity."""

    name: str = Field(..., min_length=1, description="Allergy name")
    severity: str = Field("mild", description="Severity: mild, moderate, severe")


class MedicalHistoryQuestionnaire(BaseModel):
    """Medical history questionnaire for new member."""

    conditions: str | None = Field(None, description="Existing medical conditions")
    allergies: str | None = Field(None, description="Known allergies (free-text)")
    current_medications: str | None = Field(None, description="Current medications")
    past_surgeries: str | None = Field(None, description="Past surgical procedures")
    blood_group: str | None = Field(None, description="Blood group (e.g. A+, O-)")
    family_history: str | None = Field(None, description="Family medical history")


class FamilyMemberCreate(BaseModel):
    """Family member creation request."""

    first_name: str = Field(..., min_length=1, max_length=50, description="First name")
    last_name: str = Field(..., min_length=1, max_length=50, description="Last name")
    date_of_birth: date = Field(..., description="Date of birth")
    gender: Gender = Field(..., description="Gender identity")
    relationship: Relationship = Field(..., description="Relationship to household primary")
    height_cm: float | None = Field(None, ge=30, le=300, description="Height in cm")
    weight_kg: float | None = Field(None, ge=1, le=500, description="Weight in kg")
    allergies: list[AllergyEntry] | None = Field(None, description="Structured allergies")
    emergency_contact_name: str | None = Field(None, max_length=100, description="Emergency contact name")
    emergency_contact_phone: str | None = Field(None, max_length=30, description="Emergency contact phone")
    notes: str | None = Field(None, description="General notes about the member")
    medical_history: MedicalHistoryQuestionnaire | None = Field(
        None, description="Initial medical history"
    )


class FamilyMemberUpdate(BaseModel):
    """Family member update request."""

    first_name: str | None = Field(None, min_length=1, max_length=50, description="First name")
    last_name: str | None = Field(None, min_length=1, max_length=50, description="Last name")
    date_of_birth: date | None = Field(None, description="Date of birth")
    gender: Gender | None = Field(None, description="Gender identity")
    relationship: Relationship | None = Field(None, description="Relationship to household primary")
    medical_history_summary: str | None = Field(None, description="Medical history summary")
    blood_group: str | None = Field(None, description="Blood group (e.g. A+, O-)")
    family_history: str | None = Field(None, description="Family medical history")
    height_cm: float | None = Field(None, ge=30, le=300, description="Height in cm")
    weight_kg: float | None = Field(None, ge=1, le=500, description="Weight in kg")
    allergies: list[AllergyEntry] | None = Field(None, description="Structured allergies")
    emergency_contact_name: str | None = Field(None, max_length=100, description="Emergency contact name")
    emergency_contact_phone: str | None = Field(None, max_length=30, description="Emergency contact phone")
    notes: str | None = Field(None, description="General notes about the member")
    is_active: bool | None = Field(None, description="Active status")


class FamilyMemberResponse(BaseModel):
    """Family member response."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: UUID = Field(..., description="Family member ID")
    household_id: UUID = Field(..., description="Household ID")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    date_of_birth: date = Field(..., description="Date of birth")
    gender: Gender = Field(..., description="Gender identity")
    relationship: Relationship = Field(..., description="Relationship to household primary", alias="relationship_type")
    medical_history_summary: str | None = Field(None, description="Medical history summary")
    blood_group: str | None = Field(None, description="Blood group (e.g. A+, O-)")
    family_history: str | None = Field(None, description="Family medical history")
    height_cm: float | None = Field(None, description="Height in cm")
    weight_kg: float | None = Field(None, description="Weight in kg")
    emergency_contact_name: str | None = Field(None, description="Emergency contact name")
    emergency_contact_phone: str | None = Field(None, description="Emergency contact phone")
    notes: str | None = Field(None, description="General notes about the member")
    is_active: bool = Field(..., description="Active status")
    created_at: datetime = Field(..., description="Creation timestamp")

    # Parsed once from the raw allergies_json column
    allergies: list[AllergyEntry] | None = Field(None, description="Structured allergies")

    @model_validator(mode="before")
    @classmethod
    def _parse_allergies(cls, data):
        """Parse allergies JSON column once during construction."""
        if isinstance(data, dict):
            raw = data.get("allergies_json")
            if isinstance(raw, str):
                try:
                    items = json.loads(raw)
                    if isinstance(items, list) and len(items) > 0:
                        data["allergies"] = [AllergyEntry(**a) for a in items]
                    else:
                        data["allergies"] = None
                except (json.JSONDecodeError, ValueError):
                    data["allergies"] = None
            # Remove allergies_json so Pydantic doesn't reject the unknown field
            data.pop("allergies_json", None)
        return data

    @computed_field
    @property
    def bmi(self) -> float | None:
        """Calculate BMI from height (cm) and weight (kg)."""
        if self.height_cm and self.weight_kg and self.height_cm > 0:
            height_m = self.height_cm / 100
            return round(self.weight_kg / (height_m * height_m), 1)
        return None

    @computed_field
    @property
    def bmi_category(self) -> str | None:
        """BMI category based on WHO classification."""
        bmi = self.bmi
        if bmi is None:
            return None
        if bmi < 18.5:
            return "Underweight"
        if bmi < 25:
            return "Normal"
        if bmi < 30:
            return "Overweight"
        return "Obese"
