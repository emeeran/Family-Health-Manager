"""Pydantic models for the AI Smart Report structured payload.

Mirrors the JSON schema requested by ``SMART_REPORT_PROMPT``
(``app/prompts/insight_prompts.py``). The models are intentionally tolerant:
collections default to empty, nested fields are optional, enums accept any
string, and ``coerce_numbers_to_str`` lets a numeric LLM value still parse.
This keeps a slightly-off model output from invalidating the whole report —
the viewer degrades to prose only when parsing fails entirely.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LabParameterValue(BaseModel):
    """A single prior measurement for a lab parameter."""

    model_config = ConfigDict(extra="ignore", coerce_numbers_to_str=True)
    date: str | None = None
    value: str | None = None


class LabParameter(BaseModel):
    """One lab test result with trend history."""

    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    name: str | None = None
    value: str | None = None
    unit: str | None = None
    date: str | None = None
    # in_range | out_of_range | borderline | critical
    status: str | None = None
    reference_range: str | None = None
    # improved | further_decreased | stable | new_abnormal | not_available
    trend: str | None = None
    previous_values: list[LabParameterValue] = Field(default_factory=list)


class SystemGlance(BaseModel):
    """Body-system roll-up shown in the "at a glance" grid."""

    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    system: str | None = None
    # needs_attention | ideal | no_data
    status: str | None = None
    summary: str | None = None
    parameters_total: int = 0
    parameters_out_of_range: int = 0
    parameters_improved: int = 0


class OrganDetail(BaseModel):
    """Lab parameters grouped by body system."""

    model_config = ConfigDict(extra="allow")
    system: str | None = None
    parameters: list[LabParameter] = Field(default_factory=list)


class ParameterInFocus(BaseModel):
    """An abnormal / noteworthy parameter with clinical context."""

    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    name: str | None = None
    system: str | None = None
    explanation: str | None = None
    significance: str | None = None
    trend_note: str | None = None
    recommendation: str | None = None


class SmartRecommendation(BaseModel):
    """A clinical recommendation with priority and rationale."""

    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    category: str | None = None
    # high | medium | low
    priority: str | None = None
    action: str | None = None
    reasoning: str | None = None


class ChronicCondition(BaseModel):
    """An existing/chronic condition surfaced from the full visit history."""

    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)
    name: str | None = None
    # active | resolved | monitoring
    status: str | None = None
    since: str | None = None
    note: str | None = None


class SmartReportData(BaseModel):
    """Top-level Smart Report payload."""

    model_config = ConfigDict(extra="allow")
    chronic_conditions: list[ChronicCondition] = Field(default_factory=list)
    systems_at_a_glance: list[SystemGlance] = Field(default_factory=list)
    organ_details: list[OrganDetail] = Field(default_factory=list)
    parameters_in_focus: list[ParameterInFocus] = Field(default_factory=list)
    recommendations: list[SmartRecommendation] = Field(default_factory=list)
