"""Tests for the extraction eval harness — metrics correctness + harness plumbing.

These run without real AI. The real-AI baseline is run manually via
``python -m tests.extraction.evaluator --real-ai``.
"""
from datetime import date

import pytest

from app.models.base import RecordType
from app.schemas.health_record import ExtractedFields

from .evaluator import evaluate
from .metrics import score_extraction


def test_perfect_extraction_scores_one():
    expected = ExtractedFields(
        record_type=RecordType.DOCTOR_VISIT,
        record_date=date(2024, 1, 15),
        diagnosis="Essential Hypertension",
        blood_pressure="130/85",
    )
    scores = score_extraction(expected, expected)
    agg = scores.aggregate()
    assert agg.tp > 0
    assert agg.fp == 0
    assert agg.fn == 0
    assert agg.precision == 1.0 and agg.recall == 1.0


def test_missing_field_is_false_negative():
    expected = ExtractedFields(diagnosis="T2DM", weight="75")
    extracted = ExtractedFields(diagnosis="T2DM")  # weight missing
    scores = score_extraction(extracted, expected)
    assert scores.fields["diagnosis"].tp == 1
    assert scores.fields["weight"].fn == 1
    assert scores.fields["weight"].tp == 0


def test_spurious_field_is_false_positive():
    expected = ExtractedFields(diagnosis="T2DM")
    extracted = ExtractedFields(diagnosis="T2DM", heart_rate="72")  # HR not expected
    scores = score_extraction(extracted, expected)
    assert scores.fields["heart_rate"].fp == 1


def test_wrong_value_is_false_negative():
    expected = ExtractedFields(weight="75")
    extracted = ExtractedFields(weight="80")  # wrong value
    scores = score_extraction(extracted, expected)
    assert scores.fields["weight"].fn == 1
    assert scores.fields["weight"].tp == 0


def test_prescriptions_match_by_medicine_name():
    expected = ExtractedFields(prescriptions=[
        {"medicine": "Amlodipine 5mg", "dosage": "1-0-1"},
        {"medicine": "Metoprolol 50mg", "dosage": "1-0-1"},
    ])
    extracted = ExtractedFields(prescriptions=[
        {"medicine": "Amlodipine 5mg", "dosage": "1-0-1"},  # match
        {"medicine": "Unknownium 10mg"},                    # spurious
    ])
    s = score_extraction(extracted, expected).fields["prescriptions"]
    assert s.tp == 1   # Amlodipine matched
    assert s.fn == 1   # Metoprolol missed
    assert s.fp == 1   # Unknownium spurious


def test_record_type_enum_normalizes():
    expected = ExtractedFields(record_type=RecordType.LAB_REPORT)
    extracted = ExtractedFields(record_type=RecordType.LAB_REPORT)
    assert score_extraction(extracted, expected).fields["record_type"].tp == 1


@pytest.mark.asyncio
async def test_evaluate_runs_over_all_golden_docs():
    """Mock mode: every golden doc maps to itself → perfect recall on present fields."""
    async def identity(text: str) -> ExtractedFields:
        from .golden_documents import GOLDEN_DOCUMENTS
        for doc in GOLDEN_DOCUMENTS:
            if doc.text == text:
                return doc.expected
        return ExtractedFields()

    rows = await evaluate(identity)
    assert len(rows) > 0
    for _name, fs in rows:
        agg = fs.aggregate()
        assert agg.fn == 0  # identity → nothing missed
        assert agg.fp == 0
