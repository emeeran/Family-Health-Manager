"""Shared serializers for ``AIInsight`` records.

Centralizes the ``{id, response, provider_used, generated_at, verification}``
payload that was previously duplicated (and drifting) across the smart-report
router, the insights router, and the member-detail service.

Also provides tolerant parsing of the Smart Report JSON payload out of the
stored ``response`` text — the Smart Report prompt emits JSON, but the model
occasionally wraps it in a code fence or trailing prose. Parsing server-side
means the frontend receives a first-class structured object instead of an
escaped string it has to re-parse.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from app.schemas.insight_sections import parse_insight_sections
from app.schemas.smart_report import SmartReportData
from app.schemas.preconsultation import PreConsultationData
from app.schemas.medication_report import MedicationReportData

if TYPE_CHECKING:
    from app.models.ai import AIInsight

logger = logging.getLogger(__name__)

# A verification still "pending" after this long is treated as unverifiable.
_PENDING_TIMEOUT_SECONDS = 300
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
# qwen3 "thinking" wrappers — stripped before JSON extraction so stray braces in
# a reasoning trace can't mislead _JSON_OBJECT_RE into grabbing the wrong span.
_REASONING_BLOCK_RE = re.compile(
    r"<(?:think|thinking|reflection)>.*?</(?:think|thinking|reflection)>",
    re.DOTALL | re.IGNORECASE,
)
_REASONING_OPEN_RE = re.compile(r"<(?:think|thinking|reflection)>.*", re.DOTALL | re.IGNORECASE)


def _pending_status(insight: "AIInsight") -> str:
    """Resolve a still-pending verification to ``pending`` or ``unverifiable``."""
    age = (
        datetime.now(timezone.utc) - insight.generated_at.replace(tzinfo=timezone.utc)
    ).total_seconds()
    return "pending" if age < _PENDING_TIMEOUT_SECONDS else "unverifiable"


def serialize_verification(insight: "AIInsight") -> dict:
    """Build the verification sub-object (the pending-timeout logic, in one place)."""
    if insight.verification_status != "pending" or insight.verification_at:
        return {
            "status": insight.verification_status,
            "claims_checked": insight.verification_claims_checked,
            "verifier_provider": insight.verification_verifier,
            "summary": insight.verification_summary,
            "warnings": json.loads(insight.verification_warnings_json)
            if insight.verification_warnings_json
            else None,
            "verified_at": insight.verification_at.isoformat() if insight.verification_at else None,
        }
    return {"status": _pending_status(insight)}


def serialize_insight_payload(insight: "AIInsight", *, include_sections: bool = True) -> dict:
    """Standard insight payload. Optionally appends parsed ``sections``."""
    payload: dict = {
        "id": str(insight.id),
        "response": insight.response,
        "provider_used": insight.provider_used,
        "generated_at": insight.generated_at.isoformat(),
        "verification": serialize_verification(insight),
        "sources": json.loads(insight.sources_json) if insight.sources_json else None,
        "freshness_as_of": insight.freshness_as_of.isoformat()
        if insight.freshness_as_of
        else None,
        "range_start": insight.range_start.isoformat() if insight.range_start else None,
    }
    if include_sections:
        payload["sections"] = parse_insight_sections(insight.response) or None
    return payload


def serialize_smart_report_payload(insight: "AIInsight") -> dict:
    """Insight payload plus a structured ``report`` object parsed from the JSON.

    On any parse failure ``report`` is ``None`` and the viewer falls back to
    rendering ``response`` as prose.
    """
    payload = serialize_insight_payload(insight, include_sections=False)
    report, _raw = parse_smart_report_response(insight.response)
    payload["report"] = report.model_dump(mode="json") if report else None
    payload["raw_response"] = insight.response
    return payload


def serialize_preconsultation_payload(insight: "AIInsight") -> dict:
    """Insight payload plus a structured ``preconsultation`` object parsed from JSON.

    On any parse failure ``preconsultation`` is ``None`` and the viewer falls
    back to rendering ``response`` as text.
    """
    payload = serialize_insight_payload(insight, include_sections=False)
    note, _raw = parse_preconsultation_response(insight.response)
    payload["preconsultation"] = note.model_dump(mode="json") if note else None
    payload["raw_response"] = insight.response
    return payload


def serialize_medication_report_payload(insight: "AIInsight") -> dict:
    """Insight payload plus a structured ``medication_report`` object parsed from JSON."""
    payload = serialize_insight_payload(insight, include_sections=False)
    report, _raw = parse_medication_report_response(insight.response)
    payload["medication_report"] = report.model_dump(mode="json") if report else None
    payload["raw_response"] = insight.response
    return payload


def _try_load_json(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _extract_json_object(raw: str) -> dict | None:
    """Tolerantly pull the first JSON object out of an LLM response.

    Drops qwen3 reasoning traces, strips a wrapping ```` ```json ```` fence, and
    falls back to the largest ``{...}`` span in surrounding prose. Returns the
    parsed dict or ``None``. Shared by every structured-report parser.
    """
    if not raw or not raw.strip():
        return None
    text = _REASONING_BLOCK_RE.sub("", raw.strip())
    text = _REASONING_OPEN_RE.sub("", text).strip()
    data = _try_load_json(text)
    if data is None and text.startswith("```"):
        inner = text.split("\n", 1)[-1] if "\n" in text else text
        inner = inner.rsplit("```", 1)[0].strip()
        data = _try_load_json(inner)
    if data is None:
        match = _JSON_OBJECT_RE.search(text)
        if match:
            data = _try_load_json(match.group(0))
    return data


_StructuredT = TypeVar("_StructuredT", bound=BaseModel)


def _parse_structured(
    raw: str, model: type[_StructuredT], label: str
) -> tuple[_StructuredT | None, str]:
    """Tolerantly parse ``raw`` into ``model`` via :func:`_extract_json_object`."""
    data = _extract_json_object(raw)
    if data is None:
        return None, raw
    try:
        return model.model_validate(data), raw
    except Exception as exc:  # pydantic.ValidationError or coercion errors
        logger.debug("%s validation failed: %s", label, exc)
        return None, raw


def parse_smart_report_response(raw: str) -> tuple[SmartReportData | None, str]:
    """Tolerantly parse a Smart Report JSON payload from an LLM response."""
    return _parse_structured(raw, SmartReportData, "Smart report")


def parse_preconsultation_response(raw: str) -> tuple[PreConsultationData | None, str]:
    """Tolerantly parse a structured pre-consultation note from an LLM response."""
    return _parse_structured(raw, PreConsultationData, "Pre-consultation")


def parse_medication_report_response(raw: str) -> tuple[MedicationReportData | None, str]:
    """Tolerantly parse a structured medication report from an LLM response."""
    return _parse_structured(raw, MedicationReportData, "Medication report")
