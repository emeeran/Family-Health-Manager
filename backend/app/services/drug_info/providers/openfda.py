"""openFDA provider — free, no API key required (one optional for higher limits).

Three endpoints, all under ``https://api.fda.gov``:
- ``/drug/enforcement.json`` — FDA recall (RES) reports.
- ``/drug/label.json``         — official FDA prescribing labels, incl. a
                                  ``drug_interactions`` section (returns HTML).
- ``/drug/event.json``         — FAERS adverse-event report counts.

openFDA returns **HTTP 404 with ``{"error": ...}`` when there are no matches**
— that is *normal* (e.g. a drug with no recalls), not a failure, so 404 maps to
an empty result rather than an error. See https://open.fda.gov/apis/.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json, strip_html

logger = logging.getLogger(__name__)

# openFDA caps any single request at 100 results; we never need that many.
_RECALL_LIMIT = 10
_EVENT_LIMIT = 15


def _base() -> str:
    return get_settings().OPENFDA_BASE_URL.rstrip("/")


def _auth_param() -> dict:
    """Optional API key — raises the no-key limits (240/min, 1k/day → 120k/day)."""
    key = get_settings().OPENFDA_API_KEY
    return {"api_key": key} if key else {}


def _quoted(term: str) -> str:
    """openFDA phrase: wrap in double quotes so multi-word terms stay one token."""
    return '"' + term.replace('"', "") + '"'


def _results(body) -> list:
    """Pull the ``results`` array out of an openFDA envelope, tolerating 404."""
    if isinstance(body, dict):
        # 404 "no matches" comes back as {"error": {...}} with no "results".
        r = body.get("results")
        if isinstance(r, list):
            return r
    return []


async def recalls(client: httpx.AsyncClient, generic_name: str) -> list[dict]:
    """Active/recent FDA recall reports matching a generic drug name."""
    if not generic_name:
        return []
    params = {
        "search": f"openfda.generic_name:{_quoted(generic_name)}",
        "limit": _RECALL_LIMIT,
        **_auth_param(),
    }
    status, body = await fetch_json(
        client, "GET", f"{_base()}/drug/enforcement.json", params=params
    )
    out: list[dict] = []
    for row in _results(body):
        out.append(
            {
                "generic_name": generic_name,
                "product_description": row.get("product_description") or "",
                "reason_for_recall": row.get("reason_for_recall") or "",
                "classification": row.get("classification") or "",
                "status": row.get("status") or "",
                "recalling_firm": row.get("recalling_firm") or "",
                "recall_initiation_date": row.get("recall_initiation_date") or "",
                "code_info": row.get("code_info") or "",
            }
        )
    return out


def _label_section(row: dict, key: str) -> str:
    """A label section is a list of HTML strings; join + strip to text."""
    val = row.get(key)
    if isinstance(val, list):
        return strip_html(" ".join(str(v) for v in val))
    return strip_html(val if isinstance(val, str) else "")


async def label(client: httpx.AsyncClient, generic_name: str) -> dict | None:
    """The most recent FDA label for a generic drug (key sections only)."""
    if not generic_name:
        return None
    params = {
        "search": f"openfda.generic_name:{_quoted(generic_name)}",
        "limit": 1,
        **_auth_param(),
    }
    status, body = await fetch_json(client, "GET", f"{_base()}/drug/label.json", params=params)
    rows = _results(body)
    if not rows:
        return None
    row = rows[0]
    # openFDA nests identification fields under a top-level "openfda" object.
    openfda_meta = row.get("openfda") if isinstance(row.get("openfda"), dict) else {}
    label_data = {
        "generic_name": generic_name,
        "brand_name": _first(openfda_meta.get("brand_name")),
        "manufacturer": _first(openfda_meta.get("manufacturer_name")),
        "indications_and_usage": _label_section(row, "indications_and_usage"),
        "warnings_and_cautions": _label_section(row, "warnings_and_cautions"),
        "boxed_warning": _label_section(row, "boxed_warning"),
        "drug_interactions": _label_section(row, "drug_interactions"),
        "dosage_and_administration": _label_section(row, "dosage_and_administration"),
        "contraindications": _label_section(row, "contraindications"),
        "effective_date": _first(row.get("effective_time")),
    }
    # Drop empty sections so the UI only renders what exists.
    label_data["sections"] = {
        k: v
        for k, v in label_data.items()
        if k not in {"generic_name", "brand_name", "manufacturer", "effective_date"} and v
    }
    return label_data


async def adverse_events(client: httpx.AsyncClient, generic_name: str) -> list[dict]:
    """Top reported adverse reactions (MedDRA preferred terms) with counts."""
    if not generic_name:
        return []
    params = {
        "search": f"patient.drug.openfda.generic_name:{_quoted(generic_name)}",
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": _EVENT_LIMIT,
        **_auth_param(),
    }
    status, body = await fetch_json(client, "GET", f"{_base()}/drug/event.json", params=params)
    out: list[dict] = []
    for row in _results(body):
        term = row.get("term")
        if not term:
            continue
        out.append({"term": term, "count": row.get("count", 0)})
    return out


def _first(val) -> str | None:
    """openFDA list fields → first element, else None."""
    if isinstance(val, list) and val:
        return str(val[0])
    if isinstance(val, str) and val:
        return val
    return None
