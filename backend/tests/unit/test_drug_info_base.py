"""Unit tests for drug_info.base — severity mapping, shape builder, HTML strip,
and the free-text → generic-name heuristic."""

from app.services.drug_info.base import SEVERITY_TO_APP, strip_html, to_drug_interaction
from app.services.drug_info.service import _heuristic_generic


def test_severity_map_covers_all_drugbank_values():
    assert SEVERITY_TO_APP == {"major": "high", "moderate": "moderate", "minor": "low"}


def test_to_drug_interaction_normalizes_severity():
    out = to_drug_interaction(
        drugs=["Warfarin", "Aspirin"],
        severity="MAJOR",
        description="Bleeding risk",
        recommendation="Monitor INR",
        source="drugbank",
        evidence_level="level_1",
    )
    assert out["severity"] == "high"
    assert out["source"] == "drugbank"
    assert out["evidence_level"] == "level_1"


def test_to_drug_interaction_unknown_severity_defaults_moderate():
    out = to_drug_interaction(
        drugs=["A", "B"],
        severity=None,
        description="d",
        recommendation="",
        source="ai",
    )
    assert out["severity"] == "moderate"
    # Empty recommendation falls back to a safe default, never blank.
    assert out["recommendation"]
    assert "evidence_level" not in out


def test_strip_html_drops_tags_and_entities_and_collapses_ws():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert strip_html("a &amp; b &lt;c&gt; &#39;q&#39;") == "a & b <c> 'q'"
    assert strip_html("  lots   of   spaces  ") == "lots of spaces"
    assert strip_html(None) == ""
    assert strip_html("") == ""


def test_heuristic_generic_strips_strength_and_form():
    assert _heuristic_generic("Warfarin 5mg") == "Warfarin"
    assert _heuristic_generic("Tab Metformin 500 mg") == "Metformin"
    assert _heuristic_generic("Amoxicillin 250mg/5ml") == "Amoxicillin"
    assert _heuristic_generic("Ciprofloxacin 500") == "Ciprofloxacin"


def test_heuristic_generic_unresolvable_returns_none():
    assert _heuristic_generic("500 mg") is None
    assert _heuristic_generic("Tab Cap") is None
    assert _heuristic_generic("") is None
