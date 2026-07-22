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


def _label_sections(row: dict, *keys: str) -> str:
    """Join several label-section keys into one block (e.g. pregnancy variants).

    Newer labels consolidate pregnancy/lactation under ``pregnancy_and_lactation``;
    older ones split it into ``pregnancy`` + ``nursing_mothers``. Merge whichever
    are present so the section is populated regardless of the label's generation.
    """
    parts = [_label_section(row, key) for key in keys]
    return " ".join(part for part in parts if part).strip()


def _drug_class(openfda_meta: dict) -> str | None:
    """Best-effort pharmacologic class from the openfda metadata.

    Prefers the established pharmacologic class (EPC), then the chemical/
    structured classes. Values look like ``["Biguanide [EPC]"]`` — keep the
    name, drop the ``[EPC]`` source tag.
    """
    for key in ("pharm_class_epc", "pharm_class_cs", "pharm_class_moa"):
        first = _first(openfda_meta.get(key))
        if first:
            return first.split(" [")[0].strip()
    return None


async def label_exists(client: httpx.AsyncClient, generic_name: str) -> bool:
    """Cheap existence check: does openFDA have ≥1 label for this generic?

    Used to validate an AI-suggested generic before caching/using it, so a
    hallucinated name can't poison lookups. Treats any request failure as
    "not found" rather than risking a false positive.
    """
    if not generic_name:
        return False
    params = {
        "search": f"openfda.generic_name:{_quoted(generic_name)}",
        "limit": 1,
        **_auth_param(),
    }
    try:
        _status, body = await fetch_json(
            client, "GET", f"{_base()}/drug/label.json", params=params
        )
        return bool(_results(body))
    except Exception:  # noqa: BLE001 — a failed probe is not a positive
        return False


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
        "drug_class": _drug_class(openfda_meta),
        "indications_and_usage": _label_section(row, "indications_and_usage"),
        "warnings_and_cautions": _label_section(row, "warnings_and_cautions"),
        "boxed_warning": _label_section(row, "boxed_warning"),
        "drug_interactions": _label_section(row, "drug_interactions"),
        "dosage_and_administration": _label_section(row, "dosage_and_administration"),
        "contraindications": _label_section(row, "contraindications"),
        "adverse_reactions": _label_section(row, "adverse_reactions"),
        "overdosage": _label_section(row, "overdosage"),
        "mechanism_of_action": _label_section(row, "mechanism_of_action"),
        "clinical_pharmacology": _label_section(row, "clinical_pharmacology"),
        "pregnancy_and_lactation": _label_sections(
            row, "pregnancy_and_lactation", "pregnancy", "nursing_mothers"
        ),
        "patient_medication_information": _label_section(row, "patient_medication_information"),
        "drug_abuse_and_dependence": _label_section(row, "drug_abuse_and_dependence"),
        "description": _label_section(row, "description"),
        "effective_date": _first(row.get("effective_time")),
    }
    # Scalars surfaced at the top of the card, not as collapsible sections.
    _meta = {"generic_name", "brand_name", "manufacturer", "drug_class", "effective_date"}
    # Drop empty sections so the UI only renders what exists.
    label_data["sections"] = {k: v for k, v in label_data.items() if k not in _meta and v}
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
