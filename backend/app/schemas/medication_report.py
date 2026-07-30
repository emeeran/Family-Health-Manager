"""Pydantic model for the structured medication-report payload.

Mirrors the JSON requested by ``MEDICATION_REPORT_PROMPT``. Tolerant like
``SmartReportData``: collections default to empty and nested fields are optional,
so a partial model output still parses; the viewer falls back to the raw
``response`` only when parsing fails entirely.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Medicine(BaseModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    name: str | None = None
    dose_schedule: str | None = None
    indication: str | None = None
    key_note: str | None = None


class MedicationInteraction(BaseModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    pair: str | None = None
    severity: str | None = None
    explanation: str | None = None
    action: str | None = None


class MedicationRecommendation(BaseModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    priority: str | None = None
    action: str | None = None


class MedicationReportData(BaseModel):
    """Top-level structured medication report."""

    model_config = ConfigDict(extra="allow")
    regimen_overview: str | None = None
    medicines: list[Medicine] = Field(default_factory=list)
    interactions: list[MedicationInteraction] = Field(default_factory=list)
    schedule_adherence: str | None = None
    safety_alerts: str | None = None
    recommendations: list[MedicationRecommendation] = Field(default_factory=list)
