"""MHRA drug safety alerts via the GOV.UK search API (UK equivalent of openFDA
recalls). Free, no key, JSON.

GOV.UK search returns MHRA news, drug alerts, and Drug Safety Update entries for
a term. ``link`` is a relative ``/government/...`` path (we absolutise it). Not
every result is a strict Class-x recall — results are press releases / drug
alerts / safety updates; filter client-side on ``format``/``document_type`` if a
narrower set is needed.

``GET {GOV_UK_SEARCH_URL}?q=<term>&filter_organisations=<MHRA id>&count=N`` →
``{results:[{title, link, description, public_timestamp, format, …}]}``.

Docs: https://www.gov.uk/api
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)

# GOV.UK content-store organisation slug for the MHRA.
_MHRA_ORG = "medicines-and-healthcare-products-regulatory-agency"


async def search(client: httpx.AsyncClient, term: str, limit: int = 5) -> list[dict]:
    """MHRA safety entries for ``term`` as ``[{title,url,description,date,format}]``."""
    if not term or not term.strip():
        return []
    params = {
        "q": term.strip(),
        "filter_organisations": _MHRA_ORG,
        "count": str(max(1, min(limit, 20))),
    }
    status, body = await fetch_json(
        client, "GET", get_settings().GOV_UK_SEARCH_URL, params=params
    )
    if not isinstance(body, dict):
        return []
    out: list[dict] = []
    for r in body.get("results") or []:
        if not isinstance(r, dict):
            continue
        link = r.get("link")
        if not link:
            continue
        url = link if link.startswith("http") else f"https://www.gov.uk{link}"
        out.append(
            {
                "title": r.get("title") or "",
                "url": url,
                "description": (r.get("description") or "").strip(),
                "date": r.get("public_timestamp") or "",
                "format": r.get("format") or "",
            }
        )
    return out
