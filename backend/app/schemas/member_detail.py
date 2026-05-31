"""Aggregated member detail response schema."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MemberDetailResponse(BaseModel):
    """Single-call aggregated response for the member detail page.

    Replaces 8 separate API calls with one parallel-gathered response.
    """

    member: dict
    health_score: int
    score_breakdown: dict | None = None
    brief_medical_history: str | None = None
    active_medications: list[dict] = Field(default_factory=list)
    active_medications_count: int = 0
    active_conditions_count: int = 0
    age: int = 0
    provider_assignments: list[dict] = Field(default_factory=list)
    risk_assessment: dict | None = None
    hba1c_history: list[dict] = Field(default_factory=list)
    drug_interactions: list[dict] = Field(default_factory=list)
    latest_insight: dict | None = None
    latest_preconsult_note: dict | None = None
    recent_records: list[dict] = Field(default_factory=list)
    upcoming_reminders: list[dict] = Field(default_factory=list)
    vaccinations: list[dict] = Field(default_factory=list)
    preventive_recommendations: list[dict] = Field(default_factory=list)
