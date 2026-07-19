"""Unit tests for robust extraction parsing.

Covers the fixes for blank extracted fields on the local qwen3 path:
- ``<think>``/``<thinking>`` tag + leading-prose stripping before JSON parsing
- lenient per-field construction (one bad field no longer discards the rest)
- flexible date/time coercion and ``record_type`` enum fallback
"""

from app.services.ai.document_extractor import parse_extraction, strip_llm_noise


def test_strip_llm_noise_removes_think_block():
    raw = '<think>reasoning {"fake": true} more</think>\n{"record_type": "lab_report"}'
    cleaned = strip_llm_noise(raw)
    assert "<think" not in cleaned
    assert cleaned.startswith('{"record_type"')


def test_strip_llm_noise_removes_unclosed_think():
    # Truncated mid-thought: unclosed tag → drop the whole tail.
    raw = '<think>blah {"still_thinking": true}'
    assert strip_llm_noise(raw) == ""


def test_strip_llm_noise_removes_markdown_fences():
    raw = '```json\n{"a": 1}\n```'
    assert strip_llm_noise(raw) == '{"a": 1}'


def test_parse_recovers_json_after_think_block():
    """qwen3 wraps output in <think> containing stray braces; real JSON must win."""
    raw = (
        "<think>The record is a lab report. I will output {\"x\": 1}.</think>\n"
        '{"record_type": "lab_report", "record_date": "2026-03-10", '
        '"lab_tests": [{"test_name": "HbA1c", "result": "8.9"}]}'
    )
    result = parse_extraction(raw, None)
    assert result.record_type is not None
    assert str(result.record_date) == "2026-03-10"
    assert result.lab_tests and result.lab_tests[0]["test_name"] == "HbA1c"


def test_parse_lenient_keeps_good_fields_when_one_is_bad():
    """A single unparseable value must not discard the rest of the extraction."""
    raw = (
        '{"record_date": "not-a-date", '
        '"diagnosis": "Type 2 diabetes", '
        '"prescriptions": [{"medicine": "Metformin", "dosage": "500mg"}]}'
    )
    result = parse_extraction(raw, None)
    assert result.record_date is None  # bad date dropped
    assert result.diagnosis == "Type 2 diabetes"
    assert result.prescriptions and result.prescriptions[0]["medicine"] == "Metformin"


def test_parse_coerces_regional_date():
    raw = '{"record_date": "10/03/2026", "diagnosis": "hypertension"}'
    result = parse_extraction(raw, None)
    assert result.record_date is not None
    assert result.diagnosis == "hypertension"


def test_parse_record_type_enum_fallback():
    """Unknown record_type becomes None without losing sibling fields."""
    raw = '{"record_type": "totally_unknown", "diagnosis": "migraine"}'
    result = parse_extraction(raw, None)
    assert result.record_type is None
    assert result.diagnosis == "migraine"


def test_parse_filters_non_dict_rows():
    """Junk inside prescriptions/lab_tests arrays is dropped, valid rows kept."""
    raw = (
        '{"prescriptions": ["not a dict", {"medicine": "Aspirin"}], '
        '"lab_tests": "should-be-a-list"}'
    )
    result = parse_extraction(raw, None)
    assert result.prescriptions == [{"medicine": "Aspirin"}]
    assert result.lab_tests is None


def test_parse_empty_returns_blank():
    assert parse_extraction("", None).has_any_data() is False
    assert parse_extraction(None, None).has_any_data() is False


def test_parse_unparseable_returns_blank():
    assert parse_extraction("totally not json at all", None).has_any_data() is False
