"""Unit tests for the health_resources providers (MedlinePlus Connect,
ClinicalTrials.gov v2, DailyMed v2). HTTP is faked — no network."""

from app.services.health_resources.providers import (
    clinicaltrials,
    dailymed,
    healthcanada,
    medlineplus,
    mhra,
)


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.content = b"x" if payload is not None else b""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    def __init__(self, handler):
        self._handler = handler

    async def request(self, method, url, params=None, headers=None, json=None):
        return self._handler(method, url, params, headers, json)


def _ok(payload):
    return lambda *a: _FakeResp(200, payload)


# ── MedlinePlus Connect ───────────────────────────────────────────────


def test_medlineplus_oid_resolution():
    assert medlineplus.resolve_oid("icd10").endswith(".6.90")
    assert medlineplus.resolve_oid("ICD-10_CM").endswith(".6.90")  # alias + normalization
    assert medlineplus.resolve_oid("rxnorm").endswith(".6.88")
    assert (
        medlineplus.resolve_oid("2.16.840.1.113883.6.1") == "2.16.840.1.113883.6.1"
    )  # OID passthrough
    assert medlineplus.resolve_oid("nonsense") is None
    assert medlineplus.resolve_oid("") is None


async def test_medlineplus_connect_parses_entries():
    body = {
        "entry": [
            {
                "title": {"_value": "Diabetes Type 2"},
                "link": [{"href": "https://medlineplus.gov/diabetes"}],
                "summary": "Patient info about diabetes.",
            }
        ]
    }
    out = await medlineplus.connect(FakeClient(_ok(body)), "icd10", "E11.9")
    assert out == [
        {
            "title": "Diabetes Type 2",
            "url": "https://medlineplus.gov/diabetes",
            "summary": "Patient info about diabetes.",
        }
    ]


async def test_medlineplus_connect_no_match_is_empty():
    # "There may not always be a match" → empty entry is normal, not an error.
    assert await medlineplus.connect(FakeClient(_ok({"entry": []})), "icd10", "E11.9") == []


async def test_medlineplus_connect_non_dict_body_is_empty():
    assert (
        await medlineplus.connect(FakeClient(lambda *a: _FakeResp(200, None)), "icd10", "E11.9")
        == []
    )


async def test_medlineplus_connect_rejects_bad_input():
    assert await medlineplus.connect(FakeClient(_ok({})), "", "E11.9") == []
    assert await medlineplus.connect(FakeClient(_ok({})), "icd10", "") == []
    assert await medlineplus.connect(FakeClient(_ok({})), "nonsense", "E11.9") == []


# ── ClinicalTrials.gov v2 ─────────────────────────────────────────────


async def test_clinicaltrials_parses_protocol_section():
    body = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT12345",
                        "briefTitle": "Drug X vs Placebo",
                    },
                    "statusModule": {"overallStatus": "RECRUITING"},
                    "conditionsModule": {"conditions": ["Diabetes Mellitus, Type 2"]},
                    "designModule": {"phases": ["PHASE2"]},
                }
            }
        ]
    }
    out = await clinicaltrials.trials(FakeClient(_ok(body)), "diabetes", 5)
    assert len(out) == 1
    t = out[0]
    assert t["nct_id"] == "NCT12345"
    assert t["title"] == "Drug X vs Placebo"
    assert t["status"] == "RECRUITING"
    assert t["phase"] == "PHASE2"
    assert t["conditions"] == ["Diabetes Mellitus, Type 2"]
    assert t["url"] == "https://clinicaltrials.gov/study/NCT12345"


async def test_clinicaltrials_empty_condition_noop():
    assert await clinicaltrials.trials(FakeClient(_ok({})), "", 5) == []
    assert await clinicaltrials.trials(FakeClient(_ok({})), "   ", 5) == []


async def test_clinicaltrials_empty_or_malformed_is_empty():
    assert await clinicaltrials.trials(FakeClient(_ok({"studies": []})), "diabetes", 5) == []
    assert (
        await clinicaltrials.trials(FakeClient(lambda *a: _FakeResp(200, None)), "diabetes", 5)
        == []
    )


# ── DailyMed v2 ───────────────────────────────────────────────────────


async def test_dailymed_parses_labels():
    body = {"data": [{"title": "Metformin Tablet", "setid": "abc-123"}]}
    out = await dailymed.labels(FakeClient(_ok(body)), "metformin", 3)
    assert out == [
        {
            "title": "Metformin Tablet",
            "setid": "abc-123",
            "url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=abc-123",
        }
    ]


async def test_dailymed_empty_name_noop():
    assert await dailymed.labels(FakeClient(_ok({})), "", 3) == []


async def test_dailymed_skips_entries_without_setid():
    body = {"data": [{"title": "No setid here"}, {"title": "OK", "setid": "xyz"}]}
    out = await dailymed.labels(FakeClient(_ok(body)), "metformin", 3)
    assert len(out) == 1 and out[0]["setid"] == "xyz"


# ── Health Canada DPD (DIN lookup) ────────────────────────────────────


async def test_healthcanada_parses_din():
    body = [
        {
            "drug_code": 71120,
            "drug_identification_number": "02246893",
            "brand_name": "APO-VERAP SR",
            "descriptor": "",
            "company_name": "APOTEX INC",
            "class_name": "Human",
            "ai_group_no": "0113846001",
            "last_update_date": "2026-06-29",
        }
    ]
    out = await healthcanada.lookup(FakeClient(_ok(body)), "02246893")
    assert out == {
        "din": "02246893",
        "brand_name": "APO-VERAP SR",
        "descriptor": "",
        "company_name": "APOTEX INC",
        "class_name": "Human",
        "drug_code": 71120,
        "ai_group_no": "0113846001",
        "last_update_date": "2026-06-29",
    }


async def test_healthcanada_rejects_non_8_digit():
    # No request should be made for an invalid DIN.
    assert (
        await healthcanada.lookup(FakeClient(lambda *a: _FakeResp(200, [{"x": 1}])), "123") is None
    )
    assert await healthcanada.lookup(FakeClient(lambda *a: _FakeResp(200, [])), "") is None


async def test_healthcanada_not_found_is_none():
    # Valid 8-digit DIN but DPD returns no product.
    assert await healthcanada.lookup(FakeClient(_ok([])), "02246893") is None
    assert (
        await healthcanada.lookup(FakeClient(lambda *a: _FakeResp(200, None)), "02246893") is None
    )


# ── MHRA (GOV.UK search) ──────────────────────────────────────────────


async def test_mhra_parses_results_and_absolutises_link():
    body = {
        "total": 1,
        "results": [
            {
                "title": "Metformin – MHRA Update",
                "link": "/government/news/metformin-mhra-update",
                "description": "MHRA update on metformin.",
                "public_timestamp": "2019-12-06T20:23:00Z",
                "format": "press_release",
            }
        ],
    }
    out = await mhra.search(FakeClient(_ok(body)), "metformin", 5)
    assert out == [
        {
            "title": "Metformin – MHRA Update",
            "url": "https://www.gov.uk/government/news/metformin-mhra-update",
            "description": "MHRA update on metformin.",
            "date": "2019-12-06T20:23:00Z",
            "format": "press_release",
        }
    ]


async def test_mhra_empty_term_noop():
    assert await mhra.search(FakeClient(_ok({})), "", 5) == []


async def test_mhra_non_dict_body_is_empty():
    assert await mhra.search(FakeClient(lambda *a: _FakeResp(200, None)), "x", 5) == []


async def test_mhra_keeps_absolute_url():
    body = {
        "results": [{"title": "T", "link": "https://other.example/x", "format": "press_release"}]
    }
    out = await mhra.search(FakeClient(_ok(body)), "x", 5)
    assert out[0]["url"] == "https://other.example/x"
