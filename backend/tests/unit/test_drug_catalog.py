"""Tests for the local drug catalog: composition parsing, the local provider,
and DrugInfoService local-first resolution + flyout shaping."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.drug_catalog import LocalDrug
from app.services.drug_info import DrugInfoService
from app.services.drug_info.composition import (
    ingredient_names,
    normalize_drug_name,
    parse_composition,
)
from app.services.drug_info.providers import local_catalog


# ---- composition parsing ----


def test_parse_composition_single():
    assert parse_composition("Metformin (500mg)") == [
        {"name": "Metformin", "strength": "500mg"}
    ]


def test_parse_composition_combination():
    assert parse_composition("Glimepiride (0.5mg) + Metformin (500mg)") == [
        {"name": "Glimepiride", "strength": "0.5mg"},
        {"name": "Metformin", "strength": "500mg"},
    ]


def test_parse_composition_no_strength():
    assert parse_composition("Amoxicillin") == [{"name": "Amoxicillin", "strength": None}]


def test_parse_composition_empty():
    assert parse_composition("") == []
    assert parse_composition("   ") == []


def test_ingredient_names_lowercase_distinct():
    assert ingredient_names("Metformin (500mg) + Voglibose (0.2mg)") == [
        "metformin",
        "voglibose",
    ]


# ---- name normalization (matching) ----


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Glycomet-GP 0.5 Tablet PR", "glycomet gp"),
        ("Parktidine", "parktidine"),
        ("Tab Metformin 500 mg", "metformin"),
        ("Bigomet -SR 1000 Tablet", "bigomet"),
        ("", ""),
    ],
)
def test_normalize_drug_name(raw, expected):
    assert normalize_drug_name(raw) == expected


# ---- flyout shaping helpers (pure) ----


def _sample_row() -> LocalDrug:
    return LocalDrug(
        product_id="DRS001",
        product_name="Glycomet-GP 0.5 Tablet PR",
        name_normalized="glycomet gp",
        composition="Glimepiride (0.5mg) + Metformin (500mg)",
        ingredients='[{"name": "Glimepiride", "strength": "0.5mg"}]',
        product_form="Tablet",
        introduction="For type 2 diabetes.",
        benefits="Controls blood sugar.",
        how_to_use="Take with food.",
        safety_advise="Do not skip meals.",
        side_effect="Nausea. Headache, hypoglycemia.",
        drug_drug_interaction="May interact with alcohol.",
        pregnancy_interaction="Unsafe in pregnancy.",
        primary_use="Antidiabetic",
    )


def test_local_label_shape():
    label = DrugInfoService(db=None)._local_label(_sample_row())
    assert label["source"] == "local"
    assert label["brand_name"] == "Glycomet-GP 0.5 Tablet PR"
    assert label["generic_name"] == "glimepiride, metformin"
    sections = label["sections"]
    assert "indications_and_usage" in sections
    assert "warnings_and_precautions" in sections
    assert sections["dosage_and_administration"] == "Take with food."


def test_local_indication_shape():
    ind = DrugInfoService(db=None)._local_indication(_sample_row())
    assert ind["source"] == "local"
    assert "diabetes" in ind["indication"]
    assert "Unsafe in pregnancy" in ind["contraindication"]  # pregnancy warning merged


def test_local_adverse_events_split():
    events = DrugInfoService(db=None)._local_adverse_events(_sample_row())
    terms = {e["term"].lower() for e in events}
    assert {"nausea", "headache", "hypoglycemia"} <= terms
    assert all(e["count"] == 0 for e in events)  # no FAERS counts locally


# ---- provider find/resolve (DB-backed) ----


async def _seed(db, **overrides):
    row = LocalDrug(
        product_id=overrides.get("product_id", "DRS001"),
        product_name=overrides.get("product_name", "Glycomet-GP 0.5 Tablet PR"),
        name_normalized=overrides.get(
            "name_normalized", normalize_drug_name(overrides.get("product_name", "Glycomet-GP 0.5 Tablet PR"))
        ),
        composition=overrides.get("composition", "Glimepiride (0.5mg) + Metformin (500mg)"),
    )
    db.add(row)
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_provider_resolve_exact(db_session):
    await _seed(db_session)
    res = await local_catalog.resolve(db_session, "Glycomet-GP 0.5 Tablet PR")
    assert res is not None
    assert res["source"] == "local"
    assert res["name"] == "glimepiride"  # primary ingredient of the combo
    assert res["ingredients"] == ["glimepiride", "metformin"]


@pytest.mark.asyncio
async def test_provider_resolve_contains_fallback(db_session):
    await _seed(db_session)
    # Shorter query still matches the longer normalized name via contains.
    res = await local_catalog.resolve(db_session, "Glycomet GP")
    assert res is not None
    assert res["name"] == "glimepiride"


@pytest.mark.asyncio
async def test_provider_resolve_miss_returns_none(db_session):
    await _seed(db_session)
    assert await local_catalog.resolve(db_session, "Totally Unknown Drug") is None


@pytest.mark.asyncio
async def test_provider_is_configured(db_session):
    assert await local_catalog.is_configured(db_session) is False
    await _seed(db_session)
    assert await local_catalog.is_configured(db_session) is True


# ---- service local-first resolution ----


@pytest.mark.asyncio
async def test_resolve_generic_prefers_local_catalog():
    """A catalog hit short-circuits ABDM/RxNorm/AI entirely."""
    svc = DrugInfoService(db=object())
    with (
        patch(
            "app.services.drug_info.service.local_catalog.resolve",
            new_callable=AsyncMock,
            return_value={"name": "glimepiride", "ingredients": ["glimepiride", "metformin"], "source": "local"},
        ) as mock_local,
        patch(
            "app.services.drug_info.service.abdm.is_configured", return_value=True
        ),  # would run if local missed
        patch(
            "app.services.drug_info.service.rxnorm.resolve",
            new_callable=AsyncMock,
            return_value={"name": "should-not-be-used"},
        ) as mock_rxnorm,
    ):
        out = await svc._resolve_generic("Glycomet-GP 0.5 Tablet PR")
    assert out == "glimepiride"
    mock_local.assert_awaited_once()
    mock_rxnorm.assert_not_awaited()  # local hit → RxNorm never tried
