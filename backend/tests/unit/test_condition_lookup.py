"""Unit tests for the disease & conditions lookup.

Covers the clinicaltables normalizer (free-text → ICD-10 + synonyms) and the
HealthResourcesService.condition_lookup orchestration (normalize → MedlinePlus
Connect assembly, caching, and graceful behaviour when no code is found).
External HTTP is faked; no network.
"""

import pytest

from app.services.health_resources import service as hrs
from app.services.health_resources.providers import clinicaltables


# Reuse the drug_info_providers fake-client shape (fetch_json calls
# client.request(method, url, params=, headers=, json=) and reads status/content/json).
class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.content = b"x" if payload is not None else b""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def request(self, method, url, params=None, headers=None, json=None):
        self.calls.append((method, url, params))
        return _FakeResp(self._payload)


@pytest.fixture
def neutral_cache(monkeypatch):
    """Cache always misses and silently swallows sets."""

    async def _get(key):
        return None

    async def _set(key, value, ttl=None):
        return None

    monkeypatch.setattr(hrs.cache, "get_async", _get)
    monkeypatch.setattr(hrs.cache, "set_async", _set)


@pytest.fixture
def stub_client(monkeypatch):
    """Replace get_drug_info_client so no real HTTP client is constructed."""
    sentinel = object()

    async def _get():
        return sentinel

    monkeypatch.setattr(hrs, "get_drug_info_client", _get)
    return sentinel


# ── clinicaltables.normalize_condition ───────────────────────────────


async def test_normalize_condition_parses_top_match():
    payload = [
        1,
        ["1234"],
        {
            "consumer_name": ["Type 2 Diabetes"],
            "icd10cm": [[{"code": "E11.9", "name": "Type 2 diabetes mellitus"}]],
            "synonyms": ["Diabetes Mellitus|T2DM"],
        },
        [["Type 2 Diabetes"]],
    ]
    out = await clinicaltables.normalize_condition(_FakeClient(payload), "diabetes")
    assert out == {
        "name": "Type 2 Diabetes",
        "icd10_code": "E11.9",
        "synonyms": ["Diabetes Mellitus", "T2DM"],
    }


async def test_normalize_condition_no_match_returns_none():
    out = await clinicaltables.normalize_condition(_FakeClient([0, [], {}]), "zzzunknown")
    assert out is None


async def test_normalize_condition_empty_input_returns_none():
    assert await clinicaltables.normalize_condition(_FakeClient([0, [], {}]), "") is None


# ── HealthResourcesService.condition_lookup ──────────────────────────


async def test_condition_lookup_assembles_topics(neutral_cache, stub_client, monkeypatch):
    async def _norm(client, term):
        return {"name": "Type 2 Diabetes", "icd10_code": "E11.9", "synonyms": ["T2DM"]}

    async def _connect(client, code_system, code, language="en"):
        assert code_system == "icd10"
        assert code == "E11.9"
        return [{"title": "Diabetes", "url": "https://medlineplus.gov/d", "summary": "s"}]

    monkeypatch.setattr(hrs.clinicaltables, "normalize_condition", _norm)
    monkeypatch.setattr(hrs.medlineplus, "connect", _connect)

    result = await hrs.HealthResourcesService().condition_lookup("type 2 diabetes")
    assert result["name"] == "Type 2 Diabetes"
    assert result["icd10_code"] == "E11.9"
    assert result["topics"][0]["url"] == "https://medlineplus.gov/d"


async def test_condition_lookup_no_code_skips_connect(neutral_cache, stub_client, monkeypatch):
    """If normalization finds no ICD-10 code, Connect is not called."""
    async def _norm(client, term):
        return {"name": "Unknown Thing", "icd10_code": None, "synonyms": []}

    async def _connect(*a, **k):
        raise AssertionError("Connect must not run without an ICD-10 code")

    monkeypatch.setattr(hrs.clinicaltables, "normalize_condition", _norm)
    monkeypatch.setattr(hrs.medlineplus, "connect", _connect)

    result = await hrs.HealthResourcesService().condition_lookup("flummox")
    assert result["icd10_code"] is None
    assert result["topics"] == []
    assert result["name"] == "Unknown Thing"


async def test_condition_lookup_cache_hit_skips_providers(stub_client, monkeypatch):
    cached = {
        "query": "asthma",
        "name": "Asthma",
        "icd10_code": "J45",
        "synonyms": [],
        "topics": [],
    }

    async def _get(key):
        return cached

    async def _set(key, value, ttl=None):
        raise AssertionError("cache set must not run on a hit")

    async def _nope(*a, **k):
        raise AssertionError("providers must not run on a cache hit")

    monkeypatch.setattr(hrs.cache, "get_async", _get)
    monkeypatch.setattr(hrs.cache, "set_async", _set)
    monkeypatch.setattr(hrs.clinicaltables, "normalize_condition", _nope)

    result = await hrs.HealthResourcesService().condition_lookup("asthma")
    assert result == cached
