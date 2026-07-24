"""RxNorm provider (NIH) — free, no key, no auth.

Used to turn a free-text medication like ``"Warfarin 5mg"`` into a stable
generic ingredient name + RxCUI. That normalized name then feeds openFDA
(recalls/labels/events), which only match well on generic names. The RxNorm
drug-drug *interaction* endpoint was retired in 2024, so this module does
**normalization only** — not interactions.

Docs: https://lwncbc.nlm.nih.gov/REST/RESTs.html
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)


def _base() -> str:
    return get_settings().RXNORM_BASE_URL.rstrip("/")


async def resolve(client: httpx.AsyncClient, name: str) -> dict | None:
    """Resolve a free-text drug name to ``{rxcui, name, tty}`` or ``None``.

    Two-step: ``approximateTerm`` (fuzzy — tolerates strengths/forms) gives a
    candidate RxCUI, then ``properties`` returns the canonical name + type. If the
    candidate is a brand or clinical-drug (not an ingredient), a third step
    resolves its active ingredient (``related?tty=IN``) so e.g. "Glucophage" →
    "metformin" rather than returning the brand name verbatim.
    """
    if not name or not name.strip():
        return None
    term = name.strip()

    status, body = await fetch_json(
        client, "GET", f"{_base()}/approximateTerm.json", params={"term": term, "maxEntries": 1}
    )
    rxcui = _first_candidate_rxcui(body)
    if not rxcui:
        return None

    status, props_body = await fetch_json(client, "GET", f"{_base()}/rxcui/{rxcui}/properties.json")
    props = props_body.get("properties") if isinstance(props_body, dict) else None
    if not isinstance(props, dict) or not props.get("name"):
        return None
    tty = props.get("tty") or ""

    # Brands / clinical drugs → resolve to the active ingredient (IN). This is
    # what downstream openFDA lookups need (a generic), and it's authoritative —
    # unlike the AI fallback, which can hallucinate a real-but-wrong generic.
    if tty and tty not in ("IN", "PIN", "MIN"):
        ingredient = await _ingredient_of(client, rxcui)
        if ingredient:
            return {"rxcui": str(props.get("rxcui") or rxcui), "name": ingredient, "tty": "IN"}
        # No ingredient found — fall through with the brand name (openFDA will
        # likely miss it, which degrades to "no data" rather than wrong data).

    return {
        "rxcui": str(props.get("rxcui") or rxcui),
        "name": props["name"],
        "tty": tty,
    }


async def _ingredient_of(client: httpx.AsyncClient, rxcui: str) -> str | None:
    """Active ingredient (IN) name for a brand/clinical-drug RxCUI, or None."""
    try:
        _status, body = await fetch_json(
            client, "GET", f"{_base()}/rxcui/{rxcui}/related.json", params={"tty": "IN"}
        )
    except Exception:  # noqa: BLE001 — a failed lookup just means no ingredient
        return None
    groups = body.get("relatedGroup", {}).get("conceptGroup", []) if isinstance(body, dict) else []
    for group in groups:
        for con in group.get("conceptProperties") or []:
            if isinstance(con, dict) and con.get("tty") == "IN" and con.get("name"):
                return con["name"]
    return None


def _first_candidate_rxcui(body) -> str | None:
    """Pull the top candidate RxCUI from an ``approximateTerm`` response."""
    if not isinstance(body, dict):
        return None
    group = body.get("approximateGroup")
    if not isinstance(group, dict):
        return None
    candidates = group.get("candidate")
    if not isinstance(candidates, list) or not candidates:
        return None
    first = candidates[0]
    if isinstance(first, dict) and first.get("rxcui"):
        return str(first["rxcui"])
    return None
