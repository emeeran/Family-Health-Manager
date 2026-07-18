"""MedlinePlus Connect (NLM) — code → patient-education health-topic links.

Free, no key. Web service at ``connect.medlineplus.gov/service``; the request
follows the HL7 Infobutton URL spec (``mainSearchCriteria.v.cs`` /
``mainSearchCriteria.v.c``). The response is an Atom-like JSON envelope:

    {"entry": [{"title": …, "link": [{"href": …}], "summary": …}, …]}

Per the docs, **"there may not always be a match for each code"** — an empty
``entry`` array is normal (not an error). A descriptive ``User-Agent`` is set on
the shared client (see ``drug_info/base.py``); without one NLM returns 200 +
empty bodies.

Docs: https://medlineplus.gov/medlineplus-connect/web-service/
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)

# Code-system OIDs accepted by MedlinePlus Connect, keyed by friendly name.
CODE_SYSTEM_OID: dict[str, str] = {
    "icd10": "2.16.840.1.113883.6.90",  # ICD-10-CM (diagnoses)
    "icd9": "2.16.840.1.113883.6.103",  # ICD-9-CM
    "snomed": "2.16.840.1.113883.6.96",  # SNOMED CT
    "loinc": "2.16.840.1.113883.6.1",  # LOINC (lab tests)
    "rxnorm": "2.16.840.1.113883.6.88",  # RxNorm (drugs, by RXCUI)
    "ndc": "2.16.840.1.113883.6.69",  # NDC (drugs)
}

# Aliases → canonical friendly names.
_NAME_ALIASES = {
    "icd10cm": "icd10",
    "snomedct": "snomed",
    "rxcui": "rxnorm",
}


def resolve_oid(code_system: str) -> str | None:
    """Friendly name (icd10/rxnorm/loinc/snomed/ndc) or raw OID → the OID to send."""
    if not code_system:
        return None
    # Already an OID ("2.16.840.1.…") → pass through.
    if code_system.startswith("2."):
        return code_system
    key = code_system.lower().replace("-", "").replace("_", "").replace(" ", "")
    key = _NAME_ALIASES.get(key, key)
    return CODE_SYSTEM_OID.get(key)


async def connect(
    client: httpx.AsyncClient,
    code_system: str,
    code: str,
    language: str = "en",
) -> list[dict]:
    """Return MedlinePlus patient-education matches for ``code`` as ``[{title,url,summary}]``."""
    oid = resolve_oid(code_system)
    if not oid or not code:
        return []
    params = {
        "mainSearchCriteria.v.cs": oid,
        "mainSearchCriteria.v.c": code,
        "knowledgeResponseType": "application/json",
    }
    if language and language != "en":
        params["informationRecipient.languageCode.c"] = language
    status, body = await fetch_json(
        client, "GET", get_settings().MEDLINEPLUS_CONNECT_URL, params=params
    )
    if not isinstance(body, dict):
        return []
    entries = body.get("entry") or []
    out: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        links = entry.get("link") or []
        url = links[0].get("href") if links and isinstance(links[0], dict) else None
        if not url:
            continue
        title = entry.get("title")
        if isinstance(title, dict):  # {"_value": "..."} form
            title = title.get("_value")
        out.append(
            {"title": str(title or ""), "url": str(url), "summary": str(entry.get("summary") or "")}
        )
    return out
