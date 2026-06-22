"""Tests for the deterministic heuristic extraction fallback.

The fallback runs when AI structured extraction returns nothing (common on
CPU-only local models). It must guarantee *something* is auto-filled whenever
there is OCR/transcription text, and never invent a wrong date.
"""

from datetime import date

from app.models.base import RecordType
from app.services.ai.document_extractor import heuristic_extract


NEURO_OCR = """APOLLO HOSPITALS : 21, Greams Lane, Off Greams Road, Chennai 600 006.
Phone: 044 2829 3333, 2829 0200 Fax: 044 2829 4429
Dr. DHANARAJ M
MD,DM
NEUROLOGY
Mr. MEERAN ESMAIL
Male, DOB: 05-JUN-1967 (58Y 11M 28D)
"""


def test_classifies_doctor_visit_and_provider_from_consultation():
    result = heuristic_extract(NEURO_OCR, "application/pdf")
    assert result.has_any_data()
    assert result.record_type is RecordType.DOCTOR_VISIT
    # Captures the single-letter initial too (not just "Dr. DHANARAJ").
    assert result.provider_name == "Dr. DHANARAJ M"


def test_dob_is_not_used_as_record_date():
    # The only date in the OCR is the DOB — it must NOT leak into record_date.
    result = heuristic_extract(NEURO_OCR, "application/pdf")
    assert result.record_date is None


def test_unambiguous_visit_date_is_extracted():
    text = "Consultation Date: 15/06/2026\nDr. Anita Rao"
    result = heuristic_extract(text, "application/pdf")
    assert result.record_date == date(2026, 6, 15)


def test_ambiguous_numeric_date_is_skipped_not_guessed():
    # 05/06 could be May 6 or Jun 5 — refuse to guess rather than be wrong.
    result = heuristic_extract("Visit 05/06/2026\nDr. X", "application/pdf")
    assert result.record_date is None


def test_named_month_date_is_parsed():
    result = heuristic_extract("Date: 02-Jun-2026\nDr. Smith", "application/pdf")
    assert result.record_date == date(2026, 6, 2)


def test_lab_report_classification():
    text = "Laboratory Report\nTest Name: Hemoglobin\nReference Range: 13-17\nSpecimen: Blood"
    result = heuristic_extract(text, "application/pdf")
    assert result.record_type is RecordType.LAB_REPORT


def test_empty_or_blank_text_yields_no_data():
    assert heuristic_extract("").has_any_data() is False
    assert heuristic_extract("   \n  ").has_any_data() is False
    assert heuristic_extract(None).has_any_data() is False  # type: ignore[arg-type]


def test_unrecognised_text_still_carries_clinical_data():
    # No doctor/date/type keywords — the raw text must still come through so the
    # form is auto-filled rather than "no readable data found".
    text = "Random note about a patient with no structure at all."
    result = heuristic_extract(text, "application/pdf")
    assert result.has_any_data() is True
    assert result.clinical_data is not None
    assert "Random note" in result.clinical_data


# ── Section-format transcription parsing + marker cleaning ────────────

from app.schemas.health_record import ExtractedFields  # noqa: E402
from app.services.ai.document_extractor import (  # noqa: E402
    _clean_markers,
    _heuristic_fallback,
    ExtractionResult,
)

SECTION_TRANSCRIPTION = """--- Provider ---
Susmi Keerthi Hospital, 12-Jan-2025

--- Patient Complaint ---
[illegible]

--- Vitals ---
BP: 103/[illegible]
Pulse: 76
Temp: 98.6
Weight: 72 kg

--- Diagnosis ---
Type 2 Diabetes Mellitus

--- Existing Conditions ---
Hypertension
"""


def test_section_transcription_classifies_doctor_visit():
    result = heuristic_extract(SECTION_TRANSCRIPTION, "application/pdf")
    assert result.record_type is RecordType.DOCTOR_VISIT


def test_section_transcription_extracts_fields():
    result = heuristic_extract(SECTION_TRANSCRIPTION, "application/pdf")
    assert result.diagnosis == "Type 2 Diabetes Mellitus"
    assert result.record_date == date(2025, 1, 12)
    assert result.provider_name == "Susmi Keerthi Hospital"
    assert result.existing_conditions == "Hypertension"
    # [illegible]-only value is dropped (not surfaced into the form).
    assert result.chief_complaint is None


def test_section_transcription_extracts_partial_vitals():
    result = heuristic_extract(SECTION_TRANSCRIPTION, "application/pdf")
    # Systolic readable, diastolic illegible -> "103/?".
    assert result.blood_pressure == "103/?"
    assert result.heart_rate == "76"
    assert result.temperature == "98.6"
    assert result.weight == "72"


def test_lab_results_section_classifies_lab_report():
    text = "--- Lab Results ---\nHbA1c: 8.9% (< 6.0%)\nGlucose: 142 mg/dL"
    result = heuristic_extract(text, "application/pdf")
    assert result.record_type is RecordType.LAB_REPORT


def test_clean_markers():
    assert _clean_markers("[illegible]") is None
    assert _clean_markers("  [illegible]  ") is None
    assert _clean_markers("103/[illegible]") == "103/?"
    assert _clean_markers("Metformin (?) 500mg") == "Metformin (?) 500mg"
    assert _clean_markers(None) is None
    assert _clean_markers("") is None


def test_heuristic_fallback_gap_fills_without_overwriting():
    # AI returned only a clinical_data summary; record_type/date/diagnosis null.
    ai = ExtractedFields(clinical_data="AI summary", diagnosis=None)
    result = ExtractionResult(extracted=ai, transcription=SECTION_TRANSCRIPTION)
    out = _heuristic_fallback(result, "garbage OCR that triggered vision", "application/pdf")

    assert out.extracted.record_type is RecordType.DOCTOR_VISIT  # backfilled
    assert out.extracted.record_date == date(2025, 1, 12)        # backfilled
    assert out.extracted.diagnosis == "Type 2 Diabetes Mellitus"  # backfilled
    assert out.extracted.clinical_data == "AI summary"           # NOT overwritten


def test_heuristic_fallback_does_not_overwrite_ai_values():
    ai = ExtractedFields(
        clinical_data="AI summary",
        record_type=RecordType.LAB_REPORT,
        diagnosis="AI diagnosis",
    )
    result = ExtractionResult(extracted=ai, transcription=SECTION_TRANSCRIPTION)
    out = _heuristic_fallback(result, None, "application/pdf")
    assert out.extracted.record_type is RecordType.LAB_REPORT  # AI wins
    assert out.extracted.diagnosis == "AI diagnosis"           # AI wins


def test_heuristic_fallback_prefers_transcription_over_bad_ocr():
    # The OCR is garbage; the transcription has the real data. Feeding the
    # transcription is what fills the fields.
    ai = ExtractedFields()
    result = ExtractionResult(extracted=ai, transcription=SECTION_TRANSCRIPTION)
    out = _heuristic_fallback(result, "@@@### $$$ unrecognizable", "application/pdf")
    assert out.extracted.diagnosis == "Type 2 Diabetes Mellitus"


def test_heuristic_fallback_cleans_transcription_display():
    ai = ExtractedFields()
    result = ExtractionResult(extracted=ai, transcription=SECTION_TRANSCRIPTION)
    out = _heuristic_fallback(result, None, "application/pdf")
    assert "[illegible]" not in (out.transcription or "")
    assert "(unreadable)" in (out.transcription or "")
