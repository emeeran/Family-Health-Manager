"""Unit tests for DrugInfoService orchestration: provider selection (DrugBank
when configured vs AI-fallback []), recall de-duplication, and RxNorm→openFDA
name resolution with heuristic fallback."""

from unittest.mock import AsyncMock, patch

from app.core.config import get_settings
from app.services.drug_info.service import DrugInfoService

# A throwaway stand-in client so the service never builds a real httpx client.
_FAKE_CLIENT = object()


def _patch_client():
    return patch(
        "app.services.drug_info.service.get_drug_info_client",
        new_callable=AsyncMock,
        return_value=_FAKE_CLIENT,
    )


def _meds(*names):
    return [{"medicine": n, "type": "Tab", "dosage": "1-0-1"} for n in names]


# ── DDI provider selection ────────────────────────────────────────────


async def test_ddi_uses_drugbank_when_key_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "DRUGBANK_API_KEY", "k")
    svc = DrugInfoService()
    with (
        _patch_client(),
        patch(
            "app.services.drug_info.service.drugbank.search_drug_id",
            new_callable=AsyncMock,
            side_effect=lambda c, name: {"Warfarin 5mg": "DB1", "Aspirin 75mg": "DB2"}[name],
        ) as mock_search,
        patch(
            "app.services.drug_info.service.drugbank.ddi",
            new_callable=AsyncMock,
            return_value=[
                {"drugs": ["Warfarin", "Aspirin"], "severity": "high", "description": "x",
                 "recommendation": "y", "source": "drugbank"}
            ],
        ) as mock_ddi,
    ):
        out = await svc.ddi(_meds("Warfarin 5mg", "Aspirin 75mg"))
    assert len(out) == 1 and out[0]["source"] == "drugbank"
    assert mock_search.await_count == 2
    mock_ddi.assert_awaited_once_with(_FAKE_CLIENT, ["DB1", "DB2"])


async def test_ddi_returns_empty_without_key_so_router_falls_back_to_ai(monkeypatch):
    monkeypatch.setattr(get_settings(), "DRUGBANK_API_KEY", "")
    svc = DrugInfoService()
    with (
        _patch_client(),
        patch("app.services.drug_info.service.drugbank.search_drug_id", new_callable=AsyncMock) as ms,
        patch("app.services.drug_info.service.drugbank.ddi", new_callable=AsyncMock) as md,
    ):
        out = await svc.ddi(_meds("Warfarin 5mg", "Aspirin 75mg"))
    assert out == []
    ms.assert_not_awaited()
    md.assert_not_awaited()


async def test_ddi_fewer_than_two_resolved_ids_returns_empty(monkeypatch):
    monkeypatch.setattr(get_settings(), "DRUGBANK_API_KEY", "k")
    svc = DrugInfoService()
    with (
        _patch_client(),
        patch(
            "app.services.drug_info.service.drugbank.search_drug_id",
            new_callable=AsyncMock,
            return_value=None,  # can't resolve either med
        ),
        patch("app.services.drug_info.service.drugbank.ddi", new_callable=AsyncMock) as md,
    ):
        out = await svc.ddi(_meds("ZZZ", "YYY"))
    assert out == []
    md.assert_not_awaited()


# ── recalls ───────────────────────────────────────────────────────────


async def test_recalls_dedups_across_meds():
    svc = DrugInfoService()
    duplicate_recall = {
        "generic_name": "metformin",
        "product_description": "Metformin 500mg",
        "reason_for_recall": "NDMA",
        "classification": "Class II",
    }

    async def fake_resolve(client, name):
        return {"Metformin 500mg": "metformin", "Glucophage 500mg": "metformin"}.get(name)

    with (
        _patch_client(),
        patch(
            "app.services.drug_info.service.rxnorm.resolve", new_callable=AsyncMock, side_effect=fake_resolve
        ),
        patch(
            "app.services.drug_info.service.openfda.recalls",
            new_callable=AsyncMock,
            return_value=[duplicate_recall],
        ) as mock_recalls,
    ):
        out = await svc.recalls(_meds("Metformin 500mg", "Glucophage 500mg"))

    # Same recall surfaced once even though two meds both matched metformin.
    assert len(out) == 1
    assert out[0]["reason_for_recall"] == "NDMA"
    assert mock_recalls.await_count == 2  # queried per-medicication then deduped


async def test_recalls_empty_when_no_resolvable_meds():
    svc = DrugInfoService()
    with (
        _patch_client(),
        patch(
            "app.services.drug_info.service.rxnorm.resolve",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.drug_info.service.openfda.recalls", new_callable=AsyncMock) as m,
    ):
        # "500 mg" has no alphabetic drug token → heuristic also yields None.
        assert await svc.recalls(_meds("500 mg")) == []
    m.assert_not_awaited()


# ── label / adverse_events resolution ─────────────────────────────────


async def test_label_resolves_via_rxnorm_then_openfda():
    svc = DrugInfoService()
    with (
        _patch_client(),
        patch(
            "app.services.drug_info.service.rxnorm.resolve",
            new_callable=AsyncMock,
            return_value={"rxcui": "1", "name": "metformin", "tty": "IN"},
        ),
        patch(
            "app.services.drug_info.service.openfda.label",
            new_callable=AsyncMock,
            return_value={"generic_name": "metformin"},
        ) as mock_label,
    ):
        label = await svc.label("Metformin 500mg")
    assert label == {"generic_name": "metformin"}
    mock_label.assert_awaited_once_with(_FAKE_CLIENT, "metformin")


async def test_label_falls_back_to_heuristic_when_rxnorm_fails():
    svc = DrugInfoService()
    with (
        _patch_client(),
        patch(
            "app.services.drug_info.service.rxnorm.resolve",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.drug_info.service.openfda.label",
            new_callable=AsyncMock,
            return_value={"generic_name": "warfarin"},
        ) as mock_label,
    ):
        label = await svc.label("Warfarin 5mg")
    assert label == {"generic_name": "warfarin"}
    # Heuristic stripped "5mg" before querying openFDA.
    mock_label.assert_awaited_once_with(_FAKE_CLIENT, "Warfarin")


async def test_adverse_events_empty_when_unresolvable():
    svc = DrugInfoService()
    with (
        _patch_client(),
        patch(
            "app.services.drug_info.service.rxnorm.resolve",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.services.drug_info.service.openfda.adverse_events", new_callable=AsyncMock) as m,
    ):
        # Free text "500 mg" has no resolvable drug → heuristic yields None.
        assert await svc.adverse_events("500 mg") == []
    m.assert_not_awaited()
