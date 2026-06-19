"""Phase 3 (lean) — OCR-quality gating + coverage-based confidence."""

from datetime import date

from app.models.base import RecordType
from app.schemas.health_record import ExtractedFields
from app.services.ai.document_extractor import (
    OCR_QUALITY_THRESHOLD,
    _ocr_quality,
    extraction_confidence,
)


def test_ocr_quality_clean_text_is_high():
    text = "Tab Amlodipine 5mg 1-0-1 after food. Diagnosis: Hypertension. BP 130/85."
    assert _ocr_quality(text) >= OCR_QUALITY_THRESHOLD


def test_ocr_quality_garbage_is_low():
    # Non-empty but mostly symbols / very sparse — must escalate to vision.
    assert _ocr_quality("@@@### $$$ %%% !! 1") < OCR_QUALITY_THRESHOLD
    assert _ocr_quality("a1") < OCR_QUALITY_THRESHOLD  # tiny


def test_ocr_quality_empty_is_zero():
    assert _ocr_quality(None) == 0.0
    assert _ocr_quality("") == 0.0


def test_extraction_confidence_empty_is_low():
    assert extraction_confidence(ExtractedFields()) == "low"


def test_extraction_confidence_rich_is_high():
    rich = ExtractedFields(
        record_type=RecordType.DOCTOR_VISIT,
        record_date=date(2024, 1, 15),
        provider_name="Test Clinic",
        diagnosis="Hypertension",
        chief_complaint="Follow-up",
        prescriptions=[{"medicine": "Amlodipine"}],
        blood_pressure="130/85",
    )
    assert extraction_confidence(rich) == "high"


def test_extraction_confidence_partial_is_medium():
    partial = ExtractedFields(
        record_type=RecordType.LAB_REPORT, record_date=date(2024, 3, 10), diagnosis="T2DM"
    )
    assert extraction_confidence(partial) == "medium"
