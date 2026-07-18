"""DailyMed v2 (NLM) — drug → full Structured Product Label (package insert) links.

Free, no key. ``GET services/v2/spls.json?drug_name=<name>&pagesize=N`` returns
``{data:[{title, setid, published_date, spl_version}]}``. The patient-facing
full label is ``drugInfo.cfm?setid=<setid>``. Richer than openFDA's summary
label endpoint (full indications/warnings/dosing/contraindications).

Docs: https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)


async def labels(
    client: httpx.AsyncClient, drug_name: str, limit: int = 3
) -> list[dict]:
    """Full-label links for ``drug_name`` as ``[{title,setid,url}]``."""
    if not drug_name or not drug_name.strip():
        return []
    params = {"drug_name": drug_name.strip(), "pagesize": str(max(1, min(limit, 10)))}
    status, body = await fetch_json(
        client, "GET", f"{get_settings().DAILYMED_BASE_URL}/spls.json", params=params
    )
    if not isinstance(body, dict):
        return []
    out: list[dict] = []
    for item in body.get("data") or []:
        if not isinstance(item, dict):
            continue
        setid = item.get("setid")
        if not setid:
            continue
        out.append(
            {
                "title": item.get("title") or "",
                "setid": str(setid),
                "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}",
            }
        )
    return out
