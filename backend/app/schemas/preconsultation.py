"""Pydantic model for the structured pre-consultation note payload.

Mirrors the JSON requested by ``PRE_CONSULT_PROMPT``. Tolerant like
``SmartReportData``: every field defaults to empty so a slightly-off model
output still parses, and the viewer falls back to the raw ``response`` text only
when parsing fails entirely.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PreConsultationData(BaseModel):
    """Structured pre-consultation note (the Hx / C/o / Ix / Rx / Q sections)."""

    model_config = ConfigDict(extra="allow")
    # Hx (MEDICAL HISTORY)
    chronic_conditions: list[str] = Field(default_factory=list)
    past_events: list[str] = Field(default_factory=list)
    # C/o (CHIEF COMPLAINTS / SYMPTOMS)
    chief_complaints: list[str] = Field(default_factory=list)
    # Ix (LAB ANOMALIES — PAST 6 MONTHS)
    lab_anomalies: list[str] = Field(default_factory=list)
    # Rx (CURRENT MEDICATIONS)
    medications: list[str] = Field(default_factory=list)
    # Q (QUESTIONS FOR CONSULTANT)
    questions: list[str] = Field(default_factory=list)
