"""Unit tests for HealthResourcesService orchestration."""

from unittest.mock import AsyncMock, patch

from app.services.health_resources.service import HealthResourcesService

_FAKE_CLIENT = object()


def _patch_client():
    return patch(
        "app.services.health_resources.service.get_drug_info_client",
        new_callable=AsyncMock,
        return_value=_FAKE_CLIENT,
    )


# ── drug_education (rxnorm → medlineplus + dailymed) ──────────────────


async def test_drug_education_chains_rxnorm_to_medlineplus_and_dailymed():
    svc = HealthResourcesService()
    with (
        _patch_client(),
        patch(
            "app.services.health_resources.service.rxnorm.resolve",
            new_callable=AsyncMock,
            return_value={"rxcui": "6809", "name": "metformin", "tty": "IN"},
        ),
        patch(
            "app.services.health_resources.service.medlineplus.connect",
            new_callable=AsyncMock,
            return_value=[{"title": "Metformin", "url": "https://medlineplus.gov/x", "summary": ""}],
        ) as mock_mp,
        patch(
            "app.services.health_resources.service.dailymed.labels",
            new_callable=AsyncMock,
            return_value=[{"title": "Metformin Tab", "setid": "s", "url": "https://dailymed/..."}],
        ) as mock_dm,
    ):
        out = await svc.drug_education("Metformin 500mg")
    assert len(out["medlineplus"]) == 1 and len(out["dailymed"]) == 1
    # MedlinePlus Connect was called with the resolved RXCUI.
    mock_mp.assert_awaited_once_with(_FAKE_CLIENT, "rxnorm", "6809")
    mock_dm.assert_awaited_once_with(_FAKE_CLIENT, "Metformin 500mg")


async def test_drug_education_skips_medlineplus_when_no_rxcui():
    svc = HealthResourcesService()
    with (
        _patch_client(),
        patch(
            "app.services.health_resources.service.rxnorm.resolve",
            new_callable=AsyncMock,
            return_value=None,  # unresolvable
        ),
        patch("app.services.health_resources.service.medlineplus.connect", new_callable=AsyncMock) as mock_mp,
        patch(
            "app.services.health_resources.service.dailymed.labels",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        out = await svc.drug_education("ZZZ unknown")
    assert out == {"medlineplus": [], "dailymed": []}
    mock_mp.assert_not_awaited()  # no RXCUI → no MedlinePlus call


async def test_drug_education_empty_input():
    assert await HealthResourcesService().drug_education("") == {"medlineplus": [], "dailymed": []}
    assert await HealthResourcesService().drug_education("   ") == {"medlineplus": [], "dailymed": []}


# ── trials / condition_info passthrough ───────────────────────────────


async def test_trials_passes_through():
    svc = HealthResourcesService()
    canned = [{"nct_id": "NCT1", "title": "T", "status": "RECRUITING", "phase": "", "conditions": [], "url": "u"}]
    with (
        _patch_client(),
        patch(
            "app.services.health_resources.service.clinicaltrials.trials",
            new_callable=AsyncMock,
            return_value=canned,
        ) as mock_t,
    ):
        out = await svc.trials("diabetes", 8)
    assert out == canned
    mock_t.assert_awaited_once_with(_FAKE_CLIENT, "diabetes", 8)


async def test_trials_empty_input():
    with _patch_client():
        assert await HealthResourcesService().trials("") == []


async def test_condition_info_passes_code_system():
    svc = HealthResourcesService()
    with (
        _patch_client(),
        patch(
            "app.services.health_resources.service.medlineplus.connect",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_mp,
    ):
        await svc.condition_info("icd10", "E11.9")
    mock_mp.assert_awaited_once_with(_FAKE_CLIENT, "icd10", "E11.9")
