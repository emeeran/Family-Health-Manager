"""Duplicate-therapy (same-class overlap) detection — pure unit tests."""

from app.services.duplicate_therapy_service import (
    classify_medication,
    detect_duplicate_therapy,
)


def _med(medicine, key=None, status="active"):
    return {"medicine": medicine, "medicine_key": key or medicine.lower(), "status": status}


def test_classify_known_generics():
    assert classify_medication("Atorvastatin 10mg") == "statin"
    assert classify_medication("Rosuvastatin") == "statin"
    assert classify_medication("Ibuprofen 400") == "NSAID"
    assert classify_medication("Losartan potassium") == "ARB"
    assert classify_medication("Enalapril") == "ACE inhibitor"
    assert classify_medication("Omeprazole") == "PPI"


def test_classify_unknown_returns_none():
    assert classify_medication("Metformin") is None
    assert classify_medication("Vitamin D") is None
    assert classify_medication("") is None


def test_flags_two_statins():
    meds = [_med("Atorvastatin 10mg"), _med("Rosuvastatin 5mg"), _med("Metformin")]
    findings = detect_duplicate_therapy(meds)
    assert len(findings) == 1
    assert findings[0].therapeutic_class == "statin"
    assert "Atorvastatin 10mg" in findings[0].medications
    assert "Rosuvastatin 5mg" in findings[0].medications


def test_flags_two_arbs():
    """Two ARBs (same class) is flagged; one ACE + one ARB is NOT — that's a
    cross-class interaction handled by the DDI checker, not same-class overlap."""
    assert len(detect_duplicate_therapy([_med("Losartan"), _med("Telmisartan")])) == 1
    assert detect_duplicate_therapy([_med("Ramipril"), _med("Losartan")]) == []


def test_ignores_inactive():
    meds = [_med("Atorvastatin"), _med("Rosuvastatin", status="discontinued")]
    assert detect_duplicate_therapy(meds) == []


def test_collapses_same_key_refill():
    """Two entries with the same medicine_key (a refill) are one med, not a dup."""
    meds = [
        _med("Atorvastatin 10mg", key="atorvastatin"),
        _med("Atorvastatin 20mg", key="atorvastatin"),
    ]
    assert detect_duplicate_therapy(meds) == []


def test_unrelated_meds_no_finding():
    meds = [_med("Metformin"), _med("Levothyroxine"), _med("Aspirin")]
    assert detect_duplicate_therapy(meds) == []


def test_multiple_classes_flagged():
    meds = [
        _med("Atorvastatin"),
        _med("Rosuvastatin"),
        _med("Ibuprofen"),
        _med("Diclofenac"),
    ]
    classes = {f.therapeutic_class for f in detect_duplicate_therapy(meds)}
    assert classes == {"statin", "NSAID"}
