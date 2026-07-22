"""Unit tests for the ABDM Drug Registry provider + its DrugInfoService wiring.

No network and no ABDM credentials required: ``fetch_json`` and the cache are
monkeypatched, and ``is_configured`` is forced True/False as needed. Sample
payloads mirror the ABDM API spec (Paracetamol → Acetaminophen).
"""


from app.services.drug_info import service as drug_service
from app.services.drug_info.providers import abdm

SAMPLE_SEARCH_ROW = {
    "brandIdentifier": "1264841000189100",
    "brandName": "Paracetamol (paracetamol) 500 mg oral tablet",
    "genericIdentifier": "322236009",
    "genericName": "Acetaminophen 500 mg oral tablet",
    "substanceIdentifier": ["387517004"],
    "substanceName": ["Acetaminophen"],
    "supplierIdentifier": "1101251000189100",
    "supplierName": "Adcco Limited",
    "matchedFields": ["brand_name"],
}

SAMPLE_BRAND_DETAIL = {
    "brand": {
        "identifier": "1264841000189100",
        "name": "Paracetamol (paracetamol) 500 mg oral tablet Adcco Limited",
        "licenseStatus": "UNKNOWN",
    },
    "generic": {
        "name": "Acetaminophen 500 mg oral tablet",
        "identifier": "322236009",
        "indication": "Used for pain relief and fever.",
        "contraIndication": "Hypersensitivity; severe hepatic impairment.",
    },
    "substances": [{"identifier": "387517004", "name": "Acetaminophen"}],
    "routeOfAdministrations": [{"name": "Oral route"}],
    "doseForm": "Oral tablet",
    "alternateDrugs": [
        {"brandIdentifier": "1282391000189100", "brandName": "37 C (paracetamol) 500 mg oral tablet"},
        {"brandIdentifier": "627921000189107", "brandName": "Ab-Par (paracetamol) 500 mg oral tablet"},
    ],
}

SAMPLE_GENERIC_DETAIL = {
    "generic": {
        "name": "Acetaminophen 500 mg oral tablet",
        "identifier": "322236009",
        "indication": "Used for pain relief and fever.",
        "contraIndication": "Hypersensitivity; severe hepatic impairment.",
    },
    "substances": [{"identifier": "387517004", "name": "Acetaminophen"}],
}


class _FakeCache:
    def __init__(self):
        self.store: dict[str, object] = {}

    async def get_async(self, key):
        return self.store.get(key)

    async def set_async(self, key, value, ttl=None):
        self.store[key] = value


def _install_fakes(monkeypatch, *, configured=True):
    """Point abdm at a canned HTTP layer + in-memory cache; return the call log."""
    calls: list[tuple[str, str]] = []

    async def fake_fetch_json(client, method, url, *, params=None, headers=None, json_body=None):
        calls.append((method, url))
        if url.endswith("/sessions"):
            return 200, {"accessToken": "test-token", "expiresIn": 3600}
        if "/search" in url:
            return 200, {"drugDetails": [SAMPLE_SEARCH_ROW], "count": 1}
        if "/brand/" in url:
            return 200, SAMPLE_BRAND_DETAIL
        if "/generic/" in url:
            return 200, SAMPLE_GENERIC_DETAIL
        return 404, None

    monkeypatch.setattr(abdm, "fetch_json", fake_fetch_json)
    fake_cache = _FakeCache()
    monkeypatch.setattr(abdm, "cache", fake_cache)
    monkeypatch.setattr(abdm, "is_configured", lambda: configured)
    return calls


# ── provider transforms ────────────────────────────────────────────────────


async def test_search_transforms_rows_and_uses_substance_as_generic(monkeypatch):
    _install_fakes(monkeypatch)
    rows = await abdm.search(object(), "Paracetamol")
    assert len(rows) == 1
    row = rows[0]
    assert row["brand_id"] == "1264841000189100"
    # generic_name is the clean ingredient (substanceName), not the strength-laden
    # genericName ("Acetaminophen 500 mg oral tablet").
    assert row["generic_name"] == "Acetaminophen"
    assert row["generic_id"] == "322236009"
    assert row["supplier_name"] == "Adcco Limited"
    assert row["substance_names"] == ["Acetaminophen"]


async def test_resolve_returns_match_with_brand_id(monkeypatch):
    _install_fakes(monkeypatch)
    hit = await abdm.resolve(object(), "Paracetamol")
    assert hit == {
        "generic_name": "Acetaminophen",
        "brand_id": "1264841000189100",
        "generic_id": "322236009",
    }


async def test_brand_detail_parses_substitutes_and_indication(monkeypatch):
    _install_fakes(monkeypatch)
    detail = await abdm.brand_detail(object(), "1264841000189100")
    assert detail is not None
    assert detail["indication"].startswith("Used for pain relief")
    assert detail["contraindication"].startswith("Hypersensitivity")
    assert detail["dose_form"] == "Oral tablet"
    assert detail["routes"] == ["Oral route"]
    assert len(detail["substitutes"]) == 2
    assert detail["substitutes"][0]["name"].startswith("37 C")


async def test_generic_detail_parses_indication(monkeypatch):
    _install_fakes(monkeypatch)
    detail = await abdm.generic_detail(object(), "322236009")
    assert detail is not None
    assert detail["generic_name"].startswith("Acetaminophen")
    assert detail["indication"].startswith("Used for pain")
    assert detail["substances"] == ["Acetaminophen"]


async def test_token_cached_so_sessions_posted_once_across_calls(monkeypatch):
    calls = _install_fakes(monkeypatch)
    await abdm.search(object(), "Paracetamol")
    await abdm.search(object(), "Ibuprofen")  # different query, same cached token
    session_posts = [c for c in calls if c[1].endswith("/sessions")]
    assert len(session_posts) == 1, "access token must be cached, not re-fetched per call"


# ── keyless / failure paths ────────────────────────────────────────────────


async def test_unconfigured_search_returns_empty(monkeypatch):
    _install_fakes(monkeypatch, configured=False)
    assert await abdm.search(object(), "Paracetamol") == []
    assert await abdm.resolve(object(), "Paracetamol") is None
    assert await abdm.brand_detail(object(), "x") is None


async def test_search_result_cached_no_second_http_call(monkeypatch):
    calls = _install_fakes(monkeypatch)
    await abdm.search(object(), "Paracetamol")
    search_calls_before = [c for c in calls if "/search" in c[1]]
    await abdm.search(object(), "Paracetamol")  # same query → cache hit
    search_calls_after = [c for c in calls if "/search" in c[1]]
    assert len(search_calls_after) == len(search_calls_before)  # no new /search HTTP call


# ── DrugInfoService wiring ─────────────────────────────────────────────────


async def test_resolve_generic_prefers_abdm(monkeypatch):
    """When ABDM is configured + resolves, RxNorm is never consulted."""
    _install_fakes(monkeypatch)

    rxnorm_called = []

    async def _rxnorm_should_not_run(client, name):
        rxnorm_called.append(name)
        return None

    monkeypatch.setattr(drug_service.rxnorm, "resolve", _rxnorm_should_not_run)
    svc = drug_service.DrugInfoService(db=None)
    generic = await svc._resolve_generic("Ropark")  # noqa: SLF001 — testing internals
    assert generic == "Acetaminophen"  # ABDM hit wins
    assert rxnorm_called == [], "RxNorm must be skipped when ABDM resolves"


async def test_resolve_generic_falls_through_to_rxnorm_on_abdm_miss(monkeypatch):
    _install_fakes(monkeypatch)

    async def _abdm_miss(client, name):
        return None

    monkeypatch.setattr(abdm, "resolve", _abdm_miss)

    async def _rxnorm_hit(client, name):
        return {"name": "ropinirole"}

    monkeypatch.setattr(drug_service.rxnorm, "resolve", _rxnorm_hit)
    svc = drug_service.DrugInfoService(db=None)
    assert await svc._resolve_generic("Ropark") == "ropinirole"


async def test_service_substitutes_and_indication_empty_when_unconfigured(monkeypatch):
    # ABDM not configured in the test env → both degrade cleanly.
    monkeypatch.setattr(abdm, "is_configured", lambda: False)
    svc = drug_service.DrugInfoService(db=None)
    assert await svc.substitutes("Paracetamol") == []
    assert await svc.indication("Paracetamol") is None
