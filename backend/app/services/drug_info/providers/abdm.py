"""ABDM Drug Registry provider — India's national drug catalog.

Ayushman Bharat Digital Mission (ABDM) maintains the official Indian drug
registry. Behind an OAuth ``client_credentials`` token it exposes brand + generic
+ substance + supplier search and detail endpoints. This provider is the
authoritative source for **Indian brand names** that US-centric sources (RxNorm,
openFDA) don't know — the "Ropark → empty flyout" gap — and adds Indian-context
indication/contraindication plus substitute (alternate) drugs.

Endpoint contract (``local/API Specification_DrugRegistry1.0.…pdf``):
- Auth: ``POST /api/hiecm/gateway/v3/sessions`` with ``clientId``/``clientSecret``
  + ``grantType=client_credentials`` and the ``REQUEST-ID``/``TIMESTAMP``/
  ``X-CM-ID`` gateway headers → ``accessToken`` (bearer, ~10h).
- ``GET /drug-registry/v1/search?q=&page=&limit=`` — brand/generic/substance/
  supplier per match.
- ``GET /drug-registry/v1/brand/{brandIdentifier}`` — generic indication +
  contraindication, dose form, route, **alternateDrugs** (substitutes).
- ``GET /drug-registry/v1/generic/{genericIdentifier}`` — indication/
  contraindication + substances.

Every method early-returns empty/``None`` when unconfigured or on any failure so
the rest of the app falls back to RxNorm/openFDA/AI with zero config.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.core.cache import cache
from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)

# HRP-ID gateway session endpoint (same for sandbox + production).
_SESSION_URL = "https://live.abdm.gov.in/api/hiecm/gateway/v3/sessions"
_TOKEN_CACHE_KEY = "abdm:access_token"
# Reuse a cached search for an hour (the catalog is stable; cuts repeat calls).
_SEARCH_TTL = 3600


def is_configured() -> bool:
    """True only when both ABDM credentials are present."""
    s = get_settings()
    return bool(s.ABDM_CLIENT_ID and s.ABDM_CLIENT_SECRET)


def _registry_base() -> str:
    """Drug-registry API base URL, from override or ABDM_ENV."""
    s = get_settings()
    if s.ABDM_DRUG_REGISTRY_BASE_URL:
        return s.ABDM_DRUG_REGISTRY_BASE_URL.rstrip("/")
    # Sandbox host carries the `sbx` segment (per the spec's concrete example);
    # production drops it. Prod values should be confirmed against ABDM docs.
    return "https://drugregistrysbx.abdm.gov.in" if s.ABDM_ENV != "production" else "https://drugregistry.abdm.gov.in"


def _cm_id() -> str:
    """Gateway ``X-CM-ID`` — ``sbx`` for sandbox, ``ABDM`` for production."""
    return "ABDM" if get_settings().ABDM_ENV == "production" else "sbx"


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with millisecond precision + trailing Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _access_token(client: httpx.AsyncClient) -> str | None:
    """Return a cached ABDM access token, fetching (and caching) one if needed.

    Returns ``None`` when unconfigured or the token call fails (caller skips).
    """
    if not is_configured():
        return None
    cached = await cache.get_async(_TOKEN_CACHE_KEY)
    if isinstance(cached, str) and cached:
        return cached
    headers = {
        "Accept": "application/json",
        "REQUEST-ID": str(uuid4()),
        "TIMESTAMP": _now_iso(),
        "X-CM-ID": _cm_id(),
    }
    s = get_settings()
    status, body = await fetch_json(
        client,
        "POST",
        _SESSION_URL,
        headers=headers,
        json_body={
            "clientId": s.ABDM_CLIENT_ID,
            "clientSecret": s.ABDM_CLIENT_SECRET,
            "grantType": "client_credentials",
        },
    )
    if status != 200 or not isinstance(body, dict):
        logger.info("ABDM session token request failed (status %s)", status)
        return None
    token = body.get("accessToken")
    if not isinstance(token, str) or not token:
        return None
    try:
        expires_in = int(body.get("expiresIn", 3600))
    except (TypeError, ValueError):
        expires_in = 3600
    # Refresh a minute before expiry so a call never lands on a stale token.
    await cache.set_async(_TOKEN_CACHE_KEY, token, ttl=max(expires_in - 60, 60))
    return token


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _search_key(name: str) -> str:
    return "abdm:search:" + " ".join(name.lower().split())


def _ingredient(row: dict) -> str | None:
    """Pure active ingredient for a search row (substance > generic first token).

    ABDM's ``genericName`` carries strength + form ("Acetaminophen 500 mg oral
    tablet"); ``substanceName`` is the clean ingredient ("Acetaminophen"), which
    is what downstream US lookups (openFDA) match on.
    """
    subs = row.get("substanceName")
    if isinstance(subs, list) and subs and isinstance(subs[0], str):
        return subs[0]
    generic = str(row.get("genericName") or "").strip()
    return generic.split()[0] if generic else None


def _transform_search_row(row: dict) -> dict:
    return {
        "brand_id": str(row.get("brandIdentifier") or ""),
        "brand_name": str(row.get("brandName") or "").strip(),
        "generic_name": _ingredient(row) or "",
        "generic_id": str(row.get("genericIdentifier") or ""),
        "supplier_name": str(row.get("supplierName") or "").strip(),
        "substance_names": [str(s) for s in (row.get("substanceName") or []) if isinstance(s, str)],
    }


async def search(client: httpx.AsyncClient, name: str) -> list[dict]:
    """Search the ABDM catalog by drug name; returns app-shaped rows (or [])."""
    if not is_configured() or not name or not name.strip():
        return []
    q = name.strip()
    cached = await cache.get_async(_search_key(q))
    if isinstance(cached, list):
        return cached
    token = await _access_token(client)
    if not token:
        return []
    status, body = await fetch_json(
        client,
        "GET",
        f"{_registry_base()}/drug-registry/v1/search",
        params={"q": q, "page": 0, "limit": 10},
        headers=_bearer(token),
    )
    if status != 200 or not isinstance(body, dict):
        return []
    rows = body.get("drugDetails")
    if not isinstance(rows, list):
        return []
    out = [_transform_search_row(r) for r in rows if isinstance(r, dict)]
    await cache.set_async(_search_key(q), out, ttl=_SEARCH_TTL)
    return out


async def resolve(client: httpx.AsyncClient, name: str) -> dict | None:
    """Best ABDM match for a free-text name → ``{generic_name, brand_id, generic_id}``.

    Prefers a row whose brand/generic name contains the cleaned query; falls back
    to the first row. ``None`` when nothing matches.
    """
    rows = await search(client, name)
    if not rows:
        return None
    needle = " ".join(name.lower().split())

    def _matches(row: dict) -> bool:
        hay = f"{row.get('brand_name', '')} {row.get('generic_name', '')}".lower()
        return needle in hay

    preferred = next((r for r in rows if _matches(r)), None)
    row = preferred or rows[0]
    if not row.get("generic_name"):
        return None
    return {
        "generic_name": row["generic_name"],
        "brand_id": row.get("brand_id") or "",
        "generic_id": row.get("generic_id") or "",
    }


def _as_list(body: dict, key: str, name_field: str = "name") -> list[str]:
    val = body.get(key)
    if not isinstance(val, list):
        return []
    out: list[str] = []
    for item in val:
        if isinstance(item, dict) and isinstance(item.get(name_field), str):
            out.append(item[name_field].strip())
        elif isinstance(item, str):
            out.append(item.strip())
    return [x for x in out if x]


async def brand_detail(client: httpx.AsyncClient, brand_id: str) -> dict | None:
    """Full brand detail incl. indication, contraindication, and substitutes."""
    if not is_configured() or not brand_id:
        return None
    token = await _access_token(client)
    if not token:
        return None
    status, body = await fetch_json(
        client,
        "GET",
        f"{_registry_base()}/drug-registry/v1/brand/{brand_id}",
        headers=_bearer(token),
    )
    if status != 200 or not isinstance(body, dict):
        return None
    brand = body.get("brand")
    if not isinstance(brand, dict):
        brand = {}
    generic = body.get("generic")
    if not isinstance(generic, dict):
        generic = {}
    subs = body.get("alternateDrugs")
    substitutes: list[dict] = []
    if isinstance(subs, list):
        for s in subs:
            if isinstance(s, dict) and s.get("brandName"):
                substitutes.append({"id": str(s.get("brandIdentifier") or ""), "name": str(s["brandName"]).strip()})
    return {
        "brand_name": str(brand.get("name") or "").strip(),
        "license_status": str(brand.get("licenseStatus") or "").strip(),
        "generic_name": str(generic.get("name") or "").strip(),
        "indication": str(generic.get("indication") or "").strip(),
        "contraindication": str(generic.get("contraIndication") or "").strip(),
        "dose_form": str(body.get("doseForm") or "").strip(),
        "routes": _as_list(body, "routeOfAdministrations"),
        "substitutes": substitutes,
    }


async def generic_detail(client: httpx.AsyncClient, generic_id: str) -> dict | None:
    """Generic detail: indication, contraindication, active substances."""
    if not is_configured() or not generic_id:
        return None
    token = await _access_token(client)
    if not token:
        return None
    status, body = await fetch_json(
        client,
        "GET",
        f"{_registry_base()}/drug-registry/v1/generic/{generic_id}",
        headers=_bearer(token),
    )
    if status != 200 or not isinstance(body, dict):
        return None
    generic = body.get("generic")
    if not isinstance(generic, dict):
        generic = {}
    return {
        "generic_name": str(generic.get("name") or "").strip(),
        "indication": str(generic.get("indication") or "").strip(),
        "contraindication": str(generic.get("contraIndication") or "").strip(),
        "substances": _as_list(body, "substances"),
    }
