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
    candidate RxCUI, then ``properties`` returns the canonical name + type.
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

    status, props_body = await fetch_json(
        client, "GET", f"{_base()}/rxcui/{rxcui}/properties.json"
    )
    props = props_body.get("properties") if isinstance(props_body, dict) else None
    if not isinstance(props, dict) or not props.get("name"):
        return None
    return {
        "rxcui": str(props.get("rxcui") or rxcui),
        "name": props["name"],
        "tty": props.get("tty") or "",
    }


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
