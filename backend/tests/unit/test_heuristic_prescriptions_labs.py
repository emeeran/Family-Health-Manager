"""Tests for deterministic prescription + lab-test parsing in the heuristic fallback.

When the LLM's structured JSON is weak (the documented local-CPU failure mode),
prescriptions and lab tests stayed empty even though the transcription text laid
them out in ``--- Prescriptions ---`` / ``--- Lab Results ---`` sections. These
parsers backfill the two most clinically valuable array fields from that
structured transcription — pure accuracy gain, no extra LLM call — and only
ever fill when the AI returned nothing (see ``_fill_null_fields``).
"""

from app.services.ai import document_extractor as dex


# ---- prescription line parser ----


def test_parse_prescription_line_full():
    line = "Tab Metformin 500mg 1-0-1 After food 30 days"
    rows = dex._parse_prescription_section(line)
    assert rows == [
        {
            "type": "Tab",
            "medicine": "Metformin 500mg",
            "dosage": "1-0-1",
            "duration": "30 days",
            "timing": "after_food",
            "note": "",
        }
    ]


def test_parse_prescription_line_abbreviation_dosage():
    line = "Cap Amoxicillin 500mg BD 5 days"
    rows = dex._parse_prescription_section(line)
    assert rows[0]["type"] == "Cap"
    assert rows[0]["medicine"] == "Amoxicillin 500mg"
    assert rows[0]["dosage"] == "BD"
    assert rows[0]["duration"] == "5 days"
    assert rows[0]["timing"] == ""


def test_parse_prescription_section_skips_blanks_and_template():
    body = (
        "Each medicine on its own line: Type Name Dosage Duration Timing\n"
        "\n"
        "Tab Metformin 500mg 1-0-1 After food 30 days\n"
        "  \n"
        "Syp Coughlix 2 tsp TDS 5 days\n"
    )
    rows = dex._parse_prescription_section(body)
    assert len(rows) == 2
    assert {r["medicine"] for r in rows} == {"Metformin 500mg", "Coughlix 2 tsp"}


def test_parse_prescription_bare_name_only():
    # No type/dosage/duration/timing — still captures the medicine name.
    rows = dex._parse_prescription_section("Metformin 500mg")
    assert rows == [
        {
            "type": "",
            "medicine": "Metformin 500mg",
            "dosage": "",
            "duration": "",
            "timing": "",
            "note": "",
        }
    ]


# ---- lab result line parser ----


def test_parse_lab_result_with_percent_and_range():
    line = "HbA1c: 8.9% (< 6.0%)"
    rows = dex._parse_lab_result_section(line)
    assert rows == [
        {
            "test_name": "HbA1c",
            "result": "8.9",
            "units": "%",
            "ref_value": "< 6.0%",
            "note": "",
        }
    ]


def test_parse_lab_result_with_space_units():
    line = "Fasting Glucose: 142 mg/dL (70-100 mg/dL)"
    rows = dex._parse_lab_result_section(line)
    assert rows[0]["test_name"] == "Fasting Glucose"
    assert rows[0]["result"] == "142"
    assert rows[0]["units"] == "mg/dL"
    assert rows[0]["ref_value"] == "70-100 mg/dL"


def test_parse_lab_result_textual_value():
    line = "Urine Albumin: Negative"
    rows = dex._parse_lab_result_section(line)
    assert rows[0]["test_name"] == "Urine Albumin"
    assert rows[0]["result"] == "Negative"
    assert rows[0]["units"] == ""


def test_parse_lab_result_section_skips_non_result_lines():
    body = "HbA1c: 8.9% (< 6.0%)\nnot a result line at all\nFasting Glucose: 142 mg/dL (70-100 mg/dL)"
    rows = dex._parse_lab_result_section(body)
    assert len(rows) == 2
    assert [r["test_name"] for r in rows] == ["HbA1c", "Fasting Glucose"]


# ---- heuristic_extract integration ----


def test_heuristic_extracts_prescriptions_from_section():
    text = (
        "--- Provider ---\nDr. Rao\n\n"
        "--- Prescriptions ---\nTab Metformin 500mg 1-0-1 After food 30 days\n"
    )
    result = dex.heuristic_extract(text, "application/pdf")
    assert result.prescriptions and len(result.prescriptions) == 1
    assert result.prescriptions[0]["medicine"] == "Metformin 500mg"


def test_heuristic_extracts_lab_tests_from_section():
    text = "--- Lab Results ---\nHbA1c: 8.9% (< 6.0%)\n"
    result = dex.heuristic_extract(text, "application/pdf")
    assert result.lab_tests and len(result.lab_tests) == 1
    assert result.lab_tests[0]["test_name"] == "HbA1c"
    assert result.lab_tests[0]["result"] == "8.9"


def test_heuristic_prescriptions_make_has_any_data_true():
    text = "--- Prescriptions ---\nTab Metformin 500mg 1-0-1 After food 30 days\n"
    result = dex.heuristic_extract(text, "application/pdf")
    # Prescriptions alone count as data (can flip a "no data" extraction).
    assert result.has_any_data() is True


# ---- backfill gate: only when AI returned nothing ----


def test_fill_null_fields_backfills_prescriptions_when_ai_empty():
    from app.schemas.health_record import ExtractedFields

    ai = ExtractedFields()  # AI produced no prescriptions
    heur = ExtractedFields(
        prescriptions=[{"type": "Tab", "medicine": "Metformin 500mg", "dosage": "1-0-1"}]
    )
    merged, changed = dex._fill_null_fields(ai, heur)
    assert changed is True
    assert merged.prescriptions == heur.prescriptions


def test_fill_null_fields_does_not_clobber_ai_prescriptions():
    from app.schemas.health_record import ExtractedFields

    ai_rx = [{"type": "Tab", "medicine": "AI Metformin", "dosage": "1-0-1"}]
    ai = ExtractedFields(prescriptions=ai_rx)
    heur = ExtractedFields(
        prescriptions=[{"type": "Tab", "medicine": "Heuristic Metformin", "dosage": "BD"}]
    )
    merged, changed = dex._fill_null_fields(ai, heur)
    # AI already had prescriptions — heuristic must NOT overwrite or extend.
    assert changed is False
    assert merged.prescriptions == ai_rx
