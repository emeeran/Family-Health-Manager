"""Unit tests for Smart Report / insight serialization and tolerant parsing."""
import json
from datetime import datetime, timezone
from uuid import uuid4

from app.models.ai import AIInsight
from app.schemas.insight_serializers import (
    parse_smart_report_response,
    serialize_insight_payload,
    serialize_smart_report_payload,
)
from app.schemas.insight_sections import parse_insight_sections

CLEAN_REPORT = {
    "systems_at_a_glance": [
        {
            "system": "Blood Health",
            "status": "needs_attention",
            "summary": "1 of 2 out of range",
            "parameters_total": 2,
            "parameters_out_of_range": 1,
            "parameters_improved": 0,
        },
        {
            "system": "Heart Health",
            "status": "ideal",
            "summary": "All in range",
            "parameters_total": 3,
            "parameters_out_of_range": 0,
            "parameters_improved": 1,
        },
    ],
    "organ_details": [
        {
            "system": "Blood Health",
            "parameters": [
                {
                    "name": "Hemoglobin",
                    "value": "7.8",
                    "unit": "gm%",
                    "date": "10-Feb-2026",
                    "status": "out_of_range",
                    "reference_range": "12.0-16.0",
                    "trend": "further_decreased",
                    "previous_values": [{"date": "15-Jan-2026", "value": "8.2"}],
                }
            ],
        }
    ],
    "parameters_in_focus": [
        {
            "name": "Hemoglobin",
            "system": "Blood Health",
            "explanation": "Oxygen-carrying protein.",
            "significance": "Low levels reduce oxygen delivery.",
            "trend_note": "Falling",
            "recommendation": "Monitor iron.",
        }
    ],
    "recommendations": [
        {
            "category": "Blood Health",
            "priority": "high",
            "action": "Monitor Hemoglobin.",
            "reasoning": "Continues to decrease.",
        }
    ],
}

INSIGHT_MARKDOWN = (
    "1. **Health Overview**\nA 45-year-old male with T2DM.\n\n"
    "2. **Active Conditions**\nT2DM suboptimally controlled.\n\n"
    "3. **Lab Trends**\nHbA1c rising.\n\n"
    "4. **Risk Assessment**\nElevated CV risk.\n\n"
    "5. **Recommendations**\nIntensify therapy.\n\n"
    "6. **Follow-up Actions**\nEndocrine review in 2 weeks.\n"
)


def _insight(response: str) -> AIInsight:
    # id/generated_at are normally populated by the DB on flush; supply them
    # directly here since these tests never hit the session.
    return AIInsight(
        id=uuid4(),
        prompt="x",
        response=response,
        provider_used="test",
        generated_at=datetime.now(timezone.utc),
        verification_status="pending",
    )


# ── parse_smart_report_response ────────────────────────────────────────────


def test_parse_clean_json():
    report, raw = parse_smart_report_response(json.dumps(CLEAN_REPORT))
    assert report is not None
    assert len(report.systems_at_a_glance) == 2
    assert report.systems_at_a_glance[0].system == "Blood Health"
    assert report.organ_details[0].parameters[0].previous_values[0].value == "8.2"
    assert raw == json.dumps(CLEAN_REPORT)


def test_parse_fenced_json():
    fenced = f"```json\n{json.dumps(CLEAN_REPORT)}\n```"
    report, _ = parse_smart_report_response(fenced)
    assert report is not None
    assert len(report.recommendations) == 1


def test_parse_trailing_prose():
    blob = f"{json.dumps(CLEAN_REPORT)}\n\nHere is your report. Let me know."
    report, _ = parse_smart_report_response(blob)
    assert report is not None
    assert len(report.systems_at_a_glance) == 2


def test_parse_partial_object():
    partial = '{"systems_at_a_glance": [{"system": "Blood Health", "status": "ideal"}]}'
    report, _ = parse_smart_report_response(partial)
    assert report is not None
    assert report.organ_details == []
    assert report.recommendations == []
    assert report.systems_at_a_glance[0].parameters_total == 0


def test_parse_garbage_returns_none():
    report, raw = parse_smart_report_response("this is not json at all")
    assert report is None
    assert raw == "this is not json at all"


def test_parse_empty_returns_none():
    assert parse_smart_report_response("") == (None, "")
    assert parse_smart_report_response("   ") == (None, "   ")


def test_parse_numeric_value_coerced_to_str():
    payload = json.dumps(
        {"organ_details": [{"system": "Blood", "parameters": [{"name": "Hb", "value": 7.8}]}]}
    )
    report, _ = parse_smart_report_response(payload)
    assert report is not None
    assert report.organ_details[0].parameters[0].value == "7.8"


def test_parse_unknown_enum_tolerated():
    payload = json.dumps(
        {"systems_at_a_glance": [{"system": "X", "status": "critical_danger"}]}
    )
    report, _ = parse_smart_report_response(payload)
    assert report is not None
    assert report.systems_at_a_glance[0].status == "critical_danger"


# ── serialize_smart_report_payload ─────────────────────────────────────────


def test_serialize_smart_report_payload_structured():
    insight = _insight(json.dumps(CLEAN_REPORT))
    payload = serialize_smart_report_payload(insight)
    assert payload["report"] is not None
    assert payload["report"]["systems_at_a_glance"][0]["system"] == "Blood Health"
    assert payload["raw_response"] == insight.response
    assert payload["provider_used"] == "test"
    assert "verification" in payload
    assert "sections" not in payload  # smart reports don't carry sections


def test_serialize_smart_report_payload_falls_back_to_null():
    insight = _insight("definitely not json")
    payload = serialize_smart_report_payload(insight)
    assert payload["report"] is None
    assert payload["raw_response"] == "definitely not json"


# ── serialize_insight_payload (sections) ───────────────────────────────────


def test_serialize_insight_payload_includes_sections():
    insight = _insight(INSIGHT_MARKDOWN)
    payload = serialize_insight_payload(insight)
    assert payload["sections"] is not None
    assert len(payload["sections"]) == 6
    keys = [s["key"] for s in payload["sections"]]
    assert keys == ["overview", "conditions", "labs", "risk", "recommendations", "follow_up"]
    assert payload["sections"][0]["title"] == "Health Overview"


def test_sections_no_markdown_returns_none():
    insight = _insight("plain text with no sections")
    payload = serialize_insight_payload(insight)
    assert payload["sections"] is None


# ── parse_insight_sections ─────────────────────────────────────────────────


def test_parse_insight_sections_drops_preamble():
    md = "Sure, here is the report.\n\n" + INSIGHT_MARKDOWN
    sections = parse_insight_sections(md)
    assert len(sections) == 6
    assert all(s["title"] for s in sections)
