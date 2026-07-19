"""NIH Clinical Tables — free-text condition → ICD-10-CM code + synonyms.

Free, no key. ``GET /api/conditions/v3/search?terms=…&ef=icd10cm,consumer_name,
synonyms`` returns a positional JSON array:

    [total, [key_ids], {<ef field>: [per-item values]}, [displays], …]

We take the top-ranked match's consumer-facing name, its first suggested
ICD-10-CM code, and its whole-term synonyms. This is the normalization layer
that lets free-text diagnoses (e.g. "type 2 diabetes") drive the otherwise
code-only MedlinePlus Connect endpoint. 2,400+ conditions.

Docs: https://clinicaltables.nlm.nih.gov/apidoc/conditions/v3/doc.html
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.services.drug_info.base import fetch_json

logger = logging.getLogger(__name__)

_MAX_SYNONYMS = 6


def _split_synonyms(value) -> list[str]:
    """Normalise the synonyms field (pipe/semicolon string OR list) to a list."""
    if isinstance(value, list):
        return [s.strip() for s in value if isinstance(s, str) and s.strip()]
    if isinstance(value, str) and value.strip():
        # clinicaltables stores whole-term synonyms as a delimited string.
        return [p.strip() for p in value.replace(";", "|").split("|") if p.strip()]
    return []


async def normalize_condition(client: httpx.AsyncClient, term: str) -> dict | None:
    """Map a free-text condition to ``{name, icd10_code, synonyms}`` or ``None``.

    Returns only the best (top-ranked) match; the UI can re-query with a more
    specific term when the first match isn't what the user meant.
    """
    if not term or not term.strip():
        return None
    params = {"terms": term.strip(), "maxList": 1, "ef": "icd10cm,consumer_name,synonyms"}
    status, body = await fetch_json(
        client,
        "GET",
        f"{get_settings().CLINICALTABLES_BASE_URL.rstrip('/')}/api/conditions/v3/search",
        params=params,
    )
    # Positional array: [total, [key_ids], {ef_field: [values per item]}, …].
    if not isinstance(body, list) or len(body) < 3 or not isinstance(body[2], dict):
        return None
    extras = body[2]
    names = extras.get("consumer_name") or []
    if not names:
        return None
    name = str(names[0]).strip() or term.strip()

    icd10_code: str | None = None
    icd10_groups = extras.get("icd10cm") or []
    # icd10cm is [[{code, name}, …], …] — one list per returned item; take item 0's first code.
    if icd10_groups and isinstance(icd10_groups[0], list) and icd10_groups[0]:
        first = icd10_groups[0][0]
        if isinstance(first, dict):
            icd10_code = first.get("code")

    synonym_values = extras.get("synonyms") or [None]
    synonyms = _split_synonyms(synonym_values[0] if synonym_values else None)[:_MAX_SYNONYMS]

    return {"name": name, "icd10_code": icd10_code, "synonyms": synonyms}
