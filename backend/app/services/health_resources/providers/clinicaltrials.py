"""ClinicalTrials.gov v2 — condition → matching trials.

Free, no key. ``GET api/v2/studies?query.cond=<condition>&pageSize=N`` returns
``{studies:[{protocolSection:{identificationModule:{nctId,briefTitle},
statusModule:{overallStatus}, conditionsModule:{conditions},
designModule:{phases}}}]}``. We flatten ``protocolSection`` into a simple row.

Docs: https://clinicaltrials.gov/data-api/about-api
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)


async def trials(client: httpx.AsyncClient, condition: str, limit: int = 8) -> list[dict]:
    """Recruiting-relevant trials for ``condition`` as ``[{nct_id,title,status,phase,conditions,url}]``."""
    if not condition or not condition.strip():
        return []
    params = {"query.cond": condition.strip(), "pageSize": str(max(1, min(limit, 50)))}
    status, body = await fetch_json(
        client, "GET", f"{get_settings().CLINICALTRIALS_BASE_URL}/studies", params=params
    )
    if not isinstance(body, dict):
        return []
    out: list[dict] = []
    for study in body.get("studies") or []:
        if not isinstance(study, dict):
            continue
        ps = study.get("protocolSection") or {}
        ident = ps.get("identificationModule") or {}
        nct = ident.get("nctId")
        if not nct:
            continue
        phases = (ps.get("designModule") or {}).get("phases") or []
        conditions = (ps.get("conditionsModule") or {}).get("conditions") or []
        out.append(
            {
                "nct_id": nct,
                "title": ident.get("briefTitle") or "",
                "status": (ps.get("statusModule") or {}).get("overallStatus") or "",
                "phase": ", ".join(phases) if isinstance(phases, list) else str(phases),
                "conditions": conditions if isinstance(conditions, list) else [],
                "url": f"https://clinicaltrials.gov/study/{nct}",
            }
        )
    return out
