"""DrugBank Clinical API provider — paid subscription, key-gated.

The headline DDI source. Every method early-returns empty/None when
``DRUGBANK_API_KEY`` is unset so the rest of the app falls back to the free
sources (AI for interactions, openFDA for everything else) with zero config.

Endpoint contract (https://docs.drugbank.com/v1/):
- Auth: ``Authorization: <key>`` header (the raw key, **not** ``Bearer``).
- Region filter via ``?region=<code>`` (default ``us``).
- Name → ID: ``GET /drug_names/simple?q=<full name>`` — purpose-built for
  "logging medications a patient may be taking"; matches name+strength together.
- DDI: ``POST /ddi`` body ``{"drugbank_id": [...]}`` → interactions **among the
  queried set** (pairwise), severity ``major/moderate/minor``. Requires ≥2 IDs
  (a single ID returns 422).
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json, to_drug_interaction

logger = logging.getLogger(__name__)

_BASE = "https://api.drugbank.com/v1"
# DrugBank caps a /ddi query at 40 input terms — far above any family med list.
_MAX_DDI_INPUTS = 40


def _key() -> str:
    return get_settings().DRUGBANK_API_KEY


def _region() -> str:
    return get_settings().DRUGBANK_REGION or "us"


def _auth_headers() -> dict | None:
    """Return the DrugBank auth header, or None when unconfigured."""
    key = _key()
    if not key:
        return None
    # DrugBank expects the raw key in the Authorization header (not "Bearer ").
    return {"Authorization": key}


async def search_drug_id(client: httpx.AsyncClient, name: str) -> str | None:
    """Resolve a medication name (e.g. ``"Warfarin 5mg"``) to a DrugBank ID."""
    headers = _auth_headers()
    if not headers or not name:
        return None
    status, body = await fetch_json(
        client,
        "GET",
        f"{_BASE}/drug_names/simple",
        params={"region": _region(), "q": name},
        headers=headers,
    )
    if status != 200 or not isinstance(body, dict):
        return None
    products = body.get("products")
    if not isinstance(products, list) or not products:
        return None
    ingredients = products[0].get("ingredients") if isinstance(products[0], dict) else None
    if isinstance(ingredients, list) and ingredients:
        dbid = ingredients[0].get("drugbank_id") if isinstance(ingredients[0], dict) else None
        if dbid:
            return str(dbid)
    return None


async def ddi(client: httpx.AsyncClient, drug_ids: list[str]) -> list[dict]:
    """Pairwise interactions among ``drug_ids`` (DrugBank-sourced), or []."""
    headers = _auth_headers()
    if not headers:
        return []
    # DrugBank rejects <2 inputs with 422; de-dup + cap to the documented max.
    unique = list(dict.fromkeys(drug_ids))[:_MAX_DDI_INPUTS]
    if len(unique) < 2:
        return []

    status, body = await fetch_json(
        client,
        "POST",
        f"{_BASE}/ddi",
        params={"region": _region()},
        headers=headers,
        json_body={"drugbank_id": unique},
    )
    if status != 200 or not isinstance(body, dict):
        if status not in (200, 599):
            logger.info("DrugBank /ddi returned status %s for %d ids", status, len(unique))
        return []

    interactions = body.get("interactions")
    if not isinstance(interactions, list):
        return []

    out: list[dict] = []
    for item in interactions:
        if not isinstance(item, dict):
            continue
        ingredient = item.get("ingredient") or {}
        affected = item.get("affected_ingredient") or {}
        drug_a = ingredient.get("name") if isinstance(ingredient, dict) else None
        drug_b = affected.get("name") if isinstance(affected, dict) else None
        if not drug_a or not drug_b:
            continue
        out.append(
            to_drug_interaction(
                drugs=[str(drug_a), str(drug_b)],
                severity=item.get("severity"),
                description=item.get("description") or "",
                recommendation=item.get("management") or "",
                source="drugbank",
                evidence_level=item.get("evidence_level"),
            )
        )
    return out
