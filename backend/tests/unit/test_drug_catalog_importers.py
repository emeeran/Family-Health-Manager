"""Tests for the three drug-catalog importers + the shared bulk upsert."""


import pytest

from app.models.drug_catalog import LocalDrug
from app.services.drug_info.bulk_upsert import upsert_local_drugs


# ── shared bulk upsert (idempotent, test DB) ──────────────────────────────


@pytest.mark.asyncio
async def test_bulk_upsert_inserts_then_updates(db_session):
    rows = [
        {"product_id": "gh:t1", "product_name": "T One", "name_normalized": "t one"},
        {"product_id": "gh:t2", "product_name": "T Two", "name_normalized": "t two"},
    ]
    n, b = await upsert_local_drugs(db_session, rows)
    assert n == 2 and b == 1
    # Re-upsert with a change → updates in place (idempotent), no new rows.
    rows[0]["marketer"] = "NewCo"
    await upsert_local_drugs(db_session, rows)
    from sqlalchemy import select

    all_rows = (await db_session.execute(select(LocalDrug))).scalars().all()
    assert len(all_rows) == 2
    assert next(r for r in all_rows if r.product_id == "gh:t1").marketer == "NewCo"


# ── GitHub importer ──────────────────────────────────────────────────────


def test_clean_comp_joins_two_parts():
    from app.scripts.seed_drug_catalog_github import _clean_comp

    assert _clean_comp("Amoxycillin  (500mg) ", "  Clavulanic Acid (125mg)") == (
        "Amoxycillin (500mg) + Clavulanic Acid (125mg)"
    )
    assert _clean_comp("Metformin (500mg)", "") == "Metformin (500mg)"


@pytest.mark.asyncio
async def test_github_run_skips_discontinued_and_maps(monkeypatch, tmp_path):
    import app.scripts.seed_drug_catalog_github as gh

    csv_text = (
        "id,name,price(₹),Is_discontinued,manufacturer_name,type,pack_size_label,"
        "short_composition1,short_composition2\n"
        "1,Testcomb 625 Tablet,100,FALSE,TestCo,allopathy,strip of 10,"
        "Amoxycillin (500mg) ,  Clavulanic Acid (125mg)\n"
        "2,Oldmed Tablet,50,TRUE,OldCo,allopathy,strip of 5,Discontinuedone (10mg),\n"
    )
    dest = tmp_path / "ds.csv"
    dest.write_text(csv_text, encoding="utf-8")

    async def fake_download(url, d):
        d.write_text(csv_text, encoding="utf-8")

    captured: list[dict] = []

    async def fake_upsert(db, rows, batch_size=1000):
        captured.extend(rows)
        return len(rows), 1

    monkeypatch.setattr(gh, "_download", fake_download)
    monkeypatch.setattr(gh, "upsert_local_drugs", fake_upsert)

    counts = await gh.run()
    # Discontinued row skipped; only the live one mapped.
    assert len(captured) == 1
    row = captured[0]
    assert row["product_id"] == "gh:1"
    assert row["product_name"] == "Testcomb 625 Tablet"
    assert row["composition"] == "Amoxycillin (500mg) + Clavulanic Acid (125mg)"
    assert row["marketer"] == "TestCo"
    assert counts["skipped"] == 1


# ── parse.bot (drugs.com) importer ────────────────────────────────────────


def test_drugscom_to_row_maps_sections():
    from app.scripts.seed_drug_catalog_drugscom import _to_row

    details = {
        "name": "Metformin",
        "generic_name": "metformin",
        "drug_class": "Antidiabetic",
        "sections": {
            "Uses": "Lowers blood sugar.",
            "Side Effects": "Nausea.",
            "Warnings": "Rare lactic acidosis.",
            "Dosage": "Take with meals.",
        },
    }
    row = _to_row("metformin", details)
    assert row["product_id"] == "dc:metformin"
    assert row["composition"] == "metformin"
    assert row["primary_use"] == "Antidiabetic"
    assert row["introduction"] == "Lowers blood sugar."
    assert row["side_effect"] == "Nausea."
    assert row["safety_advise"] == "Rare lactic acidosis."
    assert row["how_to_use"] == "Take with meals."


@pytest.mark.asyncio
async def test_drugscom_run_refuses_without_key(monkeypatch):
    import app.scripts.seed_drug_catalog_drugscom as dc

    monkeypatch.setattr(
        dc, "get_settings", lambda: type("S", (), {"PARSE_BOT_API_KEY": "", "PARSE_BOT_BASE_URL": "x"})()
    )
    with pytest.raises(SystemExit, match="PARSE_BOT_API_KEY"):
        await dc.run(["metformin"])


# ── Kaggle importer ─────────────────────────────────────────────────────


def test_kaggle_aggregate_top_condition_and_rating():
    from app.scripts.seed_drug_catalog_kaggle import _aggregate

    reviews = [
        {"drugName": "Lexapro", "condition": "Depression", "rating": "8"},
        {"drugName": "Lexapro", "condition": "Depression", "rating": "6"},
        {"drugName": "Lexapro", "condition": "Anxiety", "rating": "7"},
        {"drugName": "Aspirin", "condition": "Pain", "rating": "9"},
    ]
    rows = {r["product_name"]: r for r in _aggregate(reviews)}
    assert rows["Lexapro"]["product_id"] == "kaggle:lexapro"
    assert rows["Lexapro"]["primary_use"] == "Depression"  # most common
    assert rows["Lexapro"]["introduction"] == "Used for: Depression"
    assert rows["Lexapro"]["fact_box"] == "★7.0 from 3 reviews"


@pytest.mark.asyncio
async def test_kaggle_run_refuses_without_token(monkeypatch):
    import app.scripts.seed_drug_catalog_kaggle as kg

    monkeypatch.setattr(kg, "_has_kaggle_auth", lambda: False)
    with pytest.raises(SystemExit, match="KAGGLE_API_TOKEN"):
        await kg.run()
