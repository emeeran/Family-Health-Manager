"""Shared httpx client + helpers for the drug-information providers.

Mirrors the ``app/services/ai/base.py`` lifecycle (lazy shared client, modest
connection pool) but kept separate so the AI client's tuning (long Ollama
timeouts, cloud failover) doesn't leak into third-party drug-info calls.

All external drug-info endpoints (openFDA, RxNorm, DrugBank) are free or
key-gated but *untrusted* HTTP calls. Providers always degrade to an empty
result on failure — never raise to the caller — because a drug-info panel going
blank is far better than a 500 on a health record the user is trying to view.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

# DrugBank reports severity as major/moderate/minor; the rest of the app uses
# high/moderate/low (see frontend DrugInteraction type). One map for all sources.
SEVERITY_TO_APP: dict[str, str] = {
    "major": "high",
    "moderate": "moderate",
    "minor": "low",
}

_DRUG_INFO_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_DRUG_INFO_TIMEOUT = 30.0  # seconds — these are fast JSON endpoints

_drug_info_client: httpx.AsyncClient | None = None
_client_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


async def get_drug_info_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client for openFDA / RxNorm / DrugBank."""
    global _drug_info_client
    async with _get_lock():
        if _drug_info_client is None or _drug_info_client.is_closed:
            _drug_info_client = httpx.AsyncClient(
                timeout=_DRUG_INFO_TIMEOUT, limits=_DRUG_INFO_LIMITS
            )
        return _drug_info_client


def to_drug_interaction(
    *,
    drugs: list[str],
    severity: str | None,
    description: str,
    recommendation: str,
    source: str,
    evidence_level: str | None = None,
) -> dict:
    """Build an app-shaped drug-interaction dict from a provider's raw fields.

    ``severity`` is normalized via :data:`SEVERITY_TO_APP`; unknown values
    default to ``moderate`` so the frontend's colour map always has a match.
    """
    app_severity = SEVERITY_TO_APP.get((severity or "").lower(), "moderate")
    interaction: dict = {
        "drugs": drugs,
        "severity": app_severity,
        "description": description,
        "recommendation": recommendation or "Consult your prescribing doctor.",
        "source": source,
    }
    if evidence_level:
        interaction["evidence_level"] = evidence_level
    return interaction


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(html: str | None) -> str:
    """Collapse an openFDA label HTML fragment to plain text.

    openFDA returns label sections (``drug_interactions``, ``warnings``, …) as
    raw HTML. We only want readable text for display, so tags are dropped and
    whitespace normalised. Empty/None input → "".
    """
    if not html:
        return ""
    text = _TAG_RE.sub(" ", html)
    # Decode the few entities openFDA actually emits in label HTML.
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return _WS_RE.sub(" ", text).strip()


async def fetch_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    json_body: dict | None = None,
    not_found_is_empty: bool = True,
) -> tuple[int, dict | list | None]:
    """Perform an HTTP request and parse JSON, surfacing the status + parsed body.

    - On a transport/connect error, logs and returns ``(599, None)`` (no raise).
    - On 404 with ``not_found_is_empty`` (the openFDA "no results" case), the
      caller typically treats that as an empty result.

    Returns ``(status_code, parsed_json_or_None)`` so each provider can apply
    its own envelope handling without re-implementing error trapping.
    """
    try:
        resp = await client.request(
            method, url, params=params, headers=headers, json=json_body
        )
    except httpx.HTTPError as exc:
        logger.warning("Drug-info request to %s failed: %s", url, type(exc).__name__)
        return 599, None

    if resp.status_code == 204 or not resp.content:
        return resp.status_code, None
    try:
        return resp.status_code, resp.json()
    except ValueError:
        logger.warning("Drug-info response from %s was not valid JSON", url)
        return resp.status_code, None


async def gather_results(
    fn: Callable[..., Awaitable], items: list
) -> list:
    """Run ``fn`` over ``items`` concurrently and flatten non-empty results.

    Each provider call is independent (one med → one openFDA recall search), so
    we fan them out. Exceptions in any single call are logged and swallowed so
    one slow/failed med doesn't blank the whole panel.
    """
    import asyncio

    async def _one(item):
        try:
            return await fn(item)
        except Exception:  # noqa: BLE001 — degrade per-item, never break the panel
            logger.warning("Drug-info lookup failed for %r", item, exc_info=True)
            return []

    batches = await asyncio.gather(*[_one(i) for i in items]) if items else []
    flat: list = []
    for batch in batches:
        if batch:
            flat.extend(batch)
    return flat
