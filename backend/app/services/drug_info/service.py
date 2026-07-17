"""DrugInfoService — thin orchestrator over the openFDA / RxNorm / DrugBank providers.

Picks the DDI source at runtime (DrugBank when a key is configured, else nothing
— the router falls back to the AI checker). Normalizes free-text medication
names to generic ingredients via RxNorm (with a strength-stripping heuristic
fallback) before querying openFDA, since openFDA matches best on generic names.
"""

from __future__ import annotations

import logging
import re

from app.core.config import get_settings
from app.services.drug_info.base import get_drug_info_client
from app.services.drug_info.providers import drugbank, openfda, rxnorm

logger = logging.getLogger(__name__)

# Tokens to drop when guessing a generic name from free text. Covers the South-
# Asian prescription forms used elsewhere in the app (Tab/Cap/Syp/Inj/…) plus
# common units, so "Warfarin 5mg" / "Tab Metformin 500 mg" → "warfarin"/"metformin".
_DOSAGE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|ug|ml|gm|g|iu|meq|%|units?)\b", re.I)
_FORM_WORDS = {
    "tab", "tabs", "tablet", "tablets", "cap", "caps", "capsule", "capsules",
    "syp", "syrup", "inj", "injection", "drops", "drop", "cream", "ointment",
    "gel", "inhaler", "puff", "spray", "suspension", "susp", "strip", "sachet",
}


class DrugInfoService:
    """Stateless drug-info lookups for a member's medication list.

    ``db`` is accepted for parity with other services (and future caching) but
    isn't used for the live external calls.
    """

    def __init__(self, db=None):
        self.db = db

    # ── drug-drug interactions (DrugBank, when configured) ──────────────

    async def ddi(self, medications: list[dict]) -> list[dict]:
        """Authoritative interactions from DrugBank, or [] to signal AI fallback.

        Returns [] (not an error) whenever DrugBank isn't configured, can't
        resolve the meds, or yields nothing — the caller then uses the AI path.
        """
        if not get_settings().DRUGBANK_API_KEY or len(medications) < 2:
            return []
        try:
            client = await get_drug_info_client()
            names = [m.get("medicine") for m in medications if m.get("medicine")]
            ids: list[str] = []
            for name in names:
                dbid = await drugbank.search_drug_id(client, name)
                if dbid:
                    ids.append(dbid)
            if len(ids) < 2:
                return []
            return await drugbank.ddi(client, ids)
        except Exception:  # noqa: BLE001 — never break a health-record view
            logger.warning("DrugBank DDI lookup failed", exc_info=True)
            return []

    # ── openFDA-backed lookups (free) ───────────────────────────────────

    async def recalls(self, medications: list[dict]) -> list[dict]:
        """FDA recall reports across all active meds, de-duplicated."""
        generics = await self._resolve_generics([m.get("medicine", "") for m in medications])
        if not generics:
            return []
        client = await get_drug_info_client()
        seen: dict[tuple, dict] = {}
        for generic in generics:
            try:
                for recall in await openfda.recalls(client, generic):
                    key = (recall.get("reason_for_recall"), recall.get("product_description"))
                    # Keep the first occurrence; surface which med matched.
                    if key not in seen:
                        recall.setdefault("matched_medications", []).append(generic)
                        seen[key] = recall
                    else:
                        seen[key].setdefault("matched_medications", []).append(generic)
            except Exception:  # noqa: BLE001 — per-med failures degrade gracefully
                logger.warning("openFDA recalls failed for %r", generic, exc_info=True)
        return list(seen.values())

    async def label(self, medicine_name: str) -> dict | None:
        """FDA prescribing label for a single med (key sections, text-only)."""
        generic = await self._resolve_generic(medicine_name)
        if not generic:
            return None
        client = await get_drug_info_client()
        try:
            return await openfda.label(client, generic)
        except Exception:  # noqa: BLE001
            logger.warning("openFDA label failed for %r", medicine_name, exc_info=True)
            return None

    async def adverse_events(self, medicine_name: str) -> list[dict]:
        """Top reported adverse reactions for a single med."""
        generic = await self._resolve_generic(medicine_name)
        if not generic:
            return []
        client = await get_drug_info_client()
        try:
            return await openfda.adverse_events(client, generic)
        except Exception:  # noqa: BLE001
            logger.warning("openFDA adverse events failed for %r", medicine_name, exc_info=True)
            return []

    # ── name normalization ─────────────────────────────────────────────

    async def _resolve_generics(self, names: list[str]) -> list[str]:
        """Distinct generic names for a med list (RxNorm → heuristic fallback)."""
        out: list[str] = []
        client = await get_drug_info_client()
        for name in names:
            generic = await self._resolve_generic(name, client=client)
            if generic and generic not in out:
                out.append(generic)
        return out

    async def _resolve_generic(self, name: str, client=None) -> str | None:
        """Generic ingredient name for ``name``, or None if unresolvable."""
        if not name or not name.strip():
            return None
        if client is None:
            client = await get_drug_info_client()
        try:
            resolved = await rxnorm.resolve(client, name)
            if resolved and resolved.get("name"):
                return resolved["name"]
        except Exception:  # noqa: BLE001 — fall through to heuristic
            logger.debug("RxNorm resolve failed for %r; using heuristic", name)
        return _heuristic_generic(name)


def _heuristic_generic(name: str) -> str | None:
    """Best-effort generic name when RxNorm can't resolve the free text."""
    cleaned = _DOSAGE_RE.sub(" ", name).lower()
    words = [w for w in re.split(r"[,\s/]+", cleaned) if w and w not in _FORM_WORDS]
    # Strip leading/trailing punctuation and keep alphabetic tokens.
    alpha = [w.strip("().-") for w in words if w.strip("().-").isalpha()]
    if not alpha:
        return None
    return alpha[0].capitalize()
