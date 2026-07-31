"""Tests for the P2 audit fixes: brace-balanced JSON extraction (replaces the
greedy regex), the structured pre-consultation / medication parsers,
``gemini_vertex_project`` memoization, and the ``.format()``-ed
``_CLINICAL_SYSTEM_NOTE`` safety guard.
"""

import json


def test_extract_first_object_balanced() -> None:
    from app.schemas.insight_serializers import _extract_first_object

    assert _extract_first_object('prefix {"a": 1} trailing') == '{"a": 1}'
    assert _extract_first_object('{"a": {"b": 2}}') == '{"a": {"b": 2}}'  # nested
    # A brace inside a JSON string must not close the object early.
    assert _extract_first_object('{"a": "} not a close"}') == '{"a": "} not a close"}'
    assert _extract_first_object("no braces here") is None
    assert _extract_first_object('{"unbalanced') is None  # no closing brace


def test_extract_first_object_is_not_greedy() -> None:
    from app.schemas.insight_serializers import _extract_first_object

    # The old greedy `\{.*\}` regex would span both braces → invalid. The
    # balanced scan stops at the first complete object.
    text = 'Here is the report: {"a": 1}. See also appendix {x}.'
    assert _extract_first_object(text) == '{"a": 1}'


def test_extract_json_object_fenced_without_language_tag() -> None:
    from app.schemas.insight_serializers import _extract_json_object

    assert _extract_json_object('```\n{"x": 2}\n```') == {"x": 2}


def test_parse_preconsultation_valid_and_garbage() -> None:
    from app.schemas.insight_serializers import parse_preconsultation_response

    pc, _ = parse_preconsultation_response(
        '{"chronic_conditions":["HTN (2020)"],"questions":["Ask about the dose"]}'
    )
    assert pc is not None
    assert pc.chronic_conditions == ["HTN (2020)"]
    assert pc.questions == ["Ask about the dose"]
    assert parse_preconsultation_response("not json at all")[0] is None


def test_parse_medication_report_valid() -> None:
    from app.schemas.insight_serializers import parse_medication_report_response

    mr, _ = parse_medication_report_response(
        '{"regimen_overview":"3 meds","medicines":[{"name":"Metformin"}],"interactions":[]}'
    )
    assert mr is not None
    assert mr.regimen_overview == "3 meds"
    assert mr.medicines[0].name == "Metformin"
    assert mr.interactions == []


def test_gemini_vertex_project_memoized(monkeypatch, tmp_path) -> None:
    import app.core.provider_keys as pk
    from app.core import config

    adc = tmp_path / "adc.json"
    adc.write_text(
        json.dumps(
            {
                "type": "authorized_user",
                "quota_project_id": "proj-xyz",
                "client_id": "c",
                "client_secret": "s",
                "refresh_token": "r",
            }
        )
    )
    s = config.get_settings()
    monkeypatch.setattr(s, "VERTEX_PROJECT", "")
    monkeypatch.setattr(s, "GEMINI_ADC_FILE", str(adc))
    monkeypatch.setattr(pk, "_vertex_project_cache", {"resolved": False, "value": ""})

    reads: list[int] = []
    orig_read = pk.Path.read_text

    def counting(self, *args, **kwargs):
        reads.append(1)
        return orig_read(self, *args, **kwargs)

    monkeypatch.setattr(pk.Path, "read_text", counting)

    p1 = pk.gemini_vertex_project()
    p2 = pk.gemini_vertex_project()
    assert p1 == "proj-xyz" == p2
    # Memoized: the ADC file is read once across two calls (was: every call).
    assert len(reads) == 1


def test_clinical_system_note_formats_safely() -> None:
    """``_CLINICAL_SYSTEM_NOTE`` is ``.format(today=...)`` at 4 call sites; a
    stray literal brace would raise ``KeyError`` across chat + insight + report
    + transcription paths."""
    from app.services.ai import _CLINICAL_SYSTEM_NOTE

    out = _CLINICAL_SYSTEM_NOTE.format(today="2026-07-31")
    assert "{today" not in out  # placeholder filled
    assert "{{" not in out and "}}" not in out  # no leftover braces
