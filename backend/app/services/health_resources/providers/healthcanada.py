"""Health Canada Drug Product Database (DPD) — exact DIN lookup.

Free, no key, JSON. ⚠️ The DPD API does **not** support name search — a
``brand_name`` query returns a multi-megabyte dump (the filter is ignored).
Only exact ``din`` / ``drug_code`` queries return small, clean responses. So
this provider resolves a Canadian product from its 8-digit DIN (printed on the
pill bottle / prescription label).

``GET {HEALTH_CANADA_DPD_URL}/drugproduct/?din=<8-digits>&lang=en&type=json``
returns a list whose first item (when the DIN exists) is::

    {drug_code, drug_identification_number, brand_name, descriptor,
     company_name, class_name, number_of_ais, ai_group_no, last_update_date}

Docs: https://health-products.canada.ca/api/documentation/dpd-documentation-en.html
"""

from __future__ import annotations

import logging
import re

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)

_DIN_RE = re.compile(r"^\d{8}$")


async def lookup(client: httpx.AsyncClient, din: str) -> dict | None:
    """Resolve a Canadian product from its 8-digit DIN, or ``None``."""
    din = (din or "").strip()
    if not _DIN_RE.match(din):
        return None
    status, body = await fetch_json(
        client,
        "GET",
        f"{get_settings().HEALTH_CANADA_DPD_URL}/drugproduct/",
        params={"din": din, "lang": "en", "type": "json"},
    )
    if not isinstance(body, list) or not body:
        return None
    row = body[0]
    if not isinstance(row, dict) or not row.get("drug_identification_number"):
        return None
    return {
        "din": row.get("drug_identification_number"),
        "brand_name": row.get("brand_name") or "",
        "descriptor": row.get("descriptor") or "",
        "company_name": row.get("company_name") or "",
        "class_name": row.get("class_name") or "",
        "drug_code": row.get("drug_code"),
        "ai_group_no": row.get("ai_group_no") or "",
        "last_update_date": row.get("last_update_date") or "",
    }
