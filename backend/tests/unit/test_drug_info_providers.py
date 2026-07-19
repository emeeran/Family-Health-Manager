"""Unit tests for the openFDA / RxNorm / DrugBank providers.

External HTTP is faked with a tiny client that routes requests to a handler —
no network, no respx dependency. ``fetch_json`` calls
``client.request(method, url, params=, headers=, json=)`` and inspects
``resp.status_code`` / ``resp.content`` / ``resp.json()``.
"""

import pytest

from app.core.config import get_settings
from app.services.drug_info.providers import drugbank, openfda, rxnorm


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        # fetch_json treats empty content as "no body"; keep it truthy when JSON exists.
        self.content = b"x" if payload is not None else b""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    """Routes requests through a handler(method, url, params, headers, json_body)."""

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    async def request(self, method, url, params=None, headers=None, json=None):
        self.calls.append((method, url, params, headers, json))
        return self._handler(method, url, params, headers, json)


def _by_url(payload_map, default_status=200):
    """Build a handler that returns a canned payload keyed by URL substring."""

    def handler(method, url, params, headers, json):
        for fragment, (status, payload) in payload_map.items():
            if fragment in url:
                return _FakeResp(status, payload)
        return _FakeResp(404, {"error": {"code": "NOT_FOUND"}})

    return handler


# ── openFDA ───────────────────────────────────────────────────────────


async def test_openfda_recalls_parses_results():
    client = FakeClient(
        _by_url(
            {
                "/drug/enforcement.json": (
                    200,
                    {
                        "results": [
                            {
                                "product_description": "Metformin 500mg",
                                "reason_for_recall": "NDMA impurity",
                                "classification": "Class II",
                                "status": "Ongoing",
                                "recalling_firm": "Acme",
                                "recall_initiation_date": "20240101",
                            }
                        ]
                    },
                )
            }
        )
    )
    recalls = await openfda.recalls(client, "metformin")
    assert len(recalls) == 1
    assert recalls[0]["reason_for_recall"] == "NDMA impurity"
    assert recalls[0]["classification"] == "Class II"
    assert recalls[0]["generic_name"] == "metformin"


async def test_openfda_recalls_404_is_empty_not_error():
    client = FakeClient(lambda *a: _FakeResp(404, {"error": {"code": "NOT_FOUND"}}))
    assert await openfda.recalls(client, "unknowndrug") == []


async def test_openfda_recalls_empty_name_is_noop():
    assert await openfda.recalls(FakeClient(lambda *a: _FakeResp(200, {})), "") == []


async def test_openfda_label_parses_and_strips_html():
    client = FakeClient(
        _by_url(
            {
                "/drug/label.json": (
                    200,
                    {
                        "results": [
                            {
                                "openfda": {
                                    "brand_name": ["Glucophage"],
                                    "manufacturer_name": ["Bristol"],
                                },
                                "effective_time": ["20230101"],
                                "indications_and_usage": ["<p>Type 2 <b>diabetes</b></p>"],
                                "drug_interactions": ["<p>Avoid <i>alcohol</i></p>"],
                                "boxed_warning": [""],
                            }
                        ]
                    },
                )
            }
        )
    )
    label = await openfda.label(client, "metformin")
    assert label is not None
    assert label["brand_name"] == "Glucophage"
    assert label["indications_and_usage"] == "Type 2 diabetes"
    assert label["drug_interactions"] == "Avoid alcohol"
    # boxed_warning was empty → dropped from the rendered sections dict.
    assert "boxed_warning" not in label["sections"]
    assert "indications_and_usage" in label["sections"]


async def test_openfda_label_extracts_full_sections_and_drug_class():
    """The expanded label pull covers the 'complete drug info' dimensions."""
    client = FakeClient(
        _by_url(
            {
                "/drug/label.json": (
                    200,
                    {
                        "results": [
                            {
                                "openfda": {
                                    "brand_name": ["Glucophage"],
                                    "manufacturer_name": ["Bristol"],
                                    "pharm_class_epc": ["Biguanide [EPC]"],
                                },
                                "effective_time": ["20230101"],
                                "indications_and_usage": ["<p>Type 2 diabetes</p>"],
                                "adverse_reactions": ["<p>Nausea, diarrhoea</p>"],
                                "mechanism_of_action": ["<p>Decreases hepatic glucose</p>"],
                                "clinical_pharmacology": ["<p>Absorption ~50%</p>"],
                                "pregnancy": ["<p>No well-controlled studies</p>"],
                                "nursing_mothers": ["<p>Excreted in milk</p>"],
                                "patient_medication_information": ["<p>Take with food</p>"],
                                "drug_abuse_and_dependence": ["<p>None expected</p>"],
                                "overdosage": ["<p>Lactic acidosis</p>"],
                                "description": ["<p>White crystalline powder</p>"],
                            }
                        ]
                    },
                )
            }
        )
    )
    label = await openfda.label(client, "metformin")
    assert label is not None
    # drug_class derived from pharm_class_epc, [EPC] tag stripped, surfaced as a scalar.
    assert label["drug_class"] == "Biguanide"
    assert "drug_class" not in label["sections"]
    # Each new section landed in the rendered sections dict, HTML-stripped.
    assert label["sections"]["adverse_reactions"] == "Nausea, diarrhoea"
    assert label["sections"]["mechanism_of_action"] == "Decreases hepatic glucose"
    assert label["sections"]["clinical_pharmacology"] == "Absorption ~50%"
    # pregnancy + nursing_mothers merged into one section regardless of order.
    assert "No well-controlled studies" in label["sections"]["pregnancy_and_lactation"]
    assert "Excreted in milk" in label["sections"]["pregnancy_and_lactation"]
    assert label["sections"]["patient_medication_information"] == "Take with food"
    assert label["sections"]["overdosage"] == "Lactic acidosis"
    assert label["sections"]["description"] == "White crystalline powder"


async def test_openfda_label_drug_class_none_without_pharm_class():
    """No pharm_class arrays → drug_class is None (not a key in sections)."""
    client = FakeClient(
        _by_url({"/drug/label.json": (200, {"results": [{"indications_and_usage": ["x"]}]})})
    )
    label = await openfda.label(client, "unknowndrug")
    assert label is not None
    assert label["drug_class"] is None


async def test_openfda_label_no_results_returns_none():
    client = FakeClient(lambda *a: _FakeResp(404, {"error": {"code": "NOT_FOUND"}}))
    assert await openfda.label(client, "unknowndrug") is None


async def test_openfda_adverse_events_parses_counts():
    client = FakeClient(
        _by_url(
            {
                "/drug/event.json": (
                    200,
                    {
                        "results": [
                            {"term": "Nausea", "count": 42},
                            {"term": "Headache", "count": 7},
                        ]
                    },
                )
            }
        )
    )
    events = await openfda.adverse_events(client, "metformin")
    assert events == [{"term": "Nausea", "count": 42}, {"term": "Headache", "count": 7}]


async def test_openfda_adverse_events_404_is_empty():
    client = FakeClient(lambda *a: _FakeResp(404, {"error": {"code": "NOT_FOUND"}}))
    assert await openfda.adverse_events(client, "unknowndrug") == []


# ── RxNorm ────────────────────────────────────────────────────────────


async def test_rxnorm_resolve_two_step():
    def handler(method, url, params, headers, json):
        if "approximateTerm" in url:
            return _FakeResp(200, {"approximateGroup": {"candidate": [{"rxcui": "11289"}]}})
        if "/rxcui/11289/properties" in url:
            return _FakeResp(
                200, {"properties": {"rxcui": "11289", "name": "warfarin", "tty": "IN"}}
            )
        return _FakeResp(404, None)

    resolved = await rxnorm.resolve(FakeClient(handler), "Warfarin 5mg")
    assert resolved == {"rxcui": "11289", "name": "warfarin", "tty": "IN"}


async def test_rxnorm_resolve_no_candidate_returns_none():
    client = FakeClient(
        _by_url({"approximateTerm": (200, {"approximateGroup": {"candidate": []}})})
    )
    assert await rxnorm.resolve(client, "ZZZ unknown") is None


async def test_rxnorm_resolve_empty_input_returns_none():
    assert await rxnorm.resolve(FakeClient(lambda *a: _FakeResp(200, {})), "") is None
    assert await rxnorm.resolve(FakeClient(lambda *a: _FakeResp(200, {})), "   ") is None


# ── DrugBank ──────────────────────────────────────────────────────────


@pytest.fixture
def drugbank_key(monkeypatch):
    """Enable the DrugBank key for the duration of a test."""
    monkeypatch.setattr(get_settings(), "DRUGBANK_API_KEY", "test-key")
    yield "test-key"


async def test_drugbank_search_drug_id_parses_first_ingredient(drugbank_key):
    client = FakeClient(
        _by_url(
            {
                "/drug_names/simple": (
                    200,
                    {
                        "products": [
                            {"ingredients": [{"drugbank_id": "DB00682", "name": "Warfarin"}]}
                        ]
                    },
                )
            }
        )
    )
    dbid = await drugbank.search_drug_id(client, "Warfarin 5mg")
    assert dbid == "DB00682"
    # Auth header carries the raw key (not "Bearer").
    _, _, _, headers, _ = client.calls[0]
    assert headers == {"Authorization": "test-key"}


async def test_drugbank_search_drug_id_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(get_settings(), "DRUGBANK_API_KEY", "")
    assert await drugbank.search_drug_id(FakeClient(lambda *a: _FakeResp(200, {})), "x") is None


async def test_drugbank_ddi_maps_severity_and_tags_source(drugbank_key):
    client = FakeClient(
        _by_url(
            {
                "/ddi": (
                    200,
                    {
                        "interactions": [
                            {
                                "ingredient": {"drugbank_id": "DB1", "name": "Warfarin"},
                                "affected_ingredient": {"drugbank_id": "DB2", "name": "Aspirin"},
                                "severity": "major",
                                "description": "Bleeding risk",
                                "management": "Monitor INR",
                                "evidence_level": "level_1",
                            }
                        ]
                    },
                )
            }
        )
    )
    out = await drugbank.ddi(client, ["DB1", "DB2"])
    assert len(out) == 1
    ix = out[0]
    assert ix["drugs"] == ["Warfarin", "Aspirin"]
    assert ix["severity"] == "high"  # major → high
    assert ix["source"] == "drugbank"
    assert ix["evidence_level"] == "level_1"


async def test_drugbank_ddi_requires_two_ids(drugbank_key):
    client = FakeClient(lambda *a: _FakeResp(200, {"interactions": []}))
    assert await drugbank.ddi(client, ["DB1"]) == []  # <2 ids → skip
    assert await drugbank.ddi(client, []) == []


async def test_drugbank_ddi_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(get_settings(), "DRUGBANK_API_KEY", "")
    assert await drugbank.ddi(FakeClient(lambda *a: _FakeResp(200, {})), ["DB1", "DB2"]) == []
