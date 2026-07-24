"""DrugInfoService — thin orchestrator over the openFDA / RxNorm / DrugBank providers.

Picks the DDI source at runtime (DrugBank when a key is configured, else nothing
— the router falls back to the AI checker). Normalizes free-text medication
names to generic ingredients via RxNorm (with a strength-stripping heuristic
fallback) before querying openFDA, since openFDA matches best on generic names.
"""

from __future__ import annotations

import logging
import re
import time

from app.core.config import get_settings
from app.services.drug_info.base import get_drug_info_client
from app.services.drug_info.providers import abdm, drugbank, openfda, rxnorm
from app.services.drug_info.providers import local_catalog
from app.services.drug_info.composition import (
    _DOSAGE_RE,
    _FORM_WORDS,
    ingredient_names,
)

logger = logging.getLogger(__name__)

# brand→generic resolved by the AI fallback (when RxNorm + heuristic can't map a
# name). Cached so each brand costs at most one AI round-trip; negatives cached
# shorter so a transient AI miss is retried. Shared across requests (module-level).
_GENERIC_AI_POS_TTL = 7 * 24 * 3600  # 7 days — brand→generic is stable
_GENERIC_AI_NEG_TTL = 24 * 3600  # 1 day — retry unresolved names sooner
_generic_ai_cache: dict[str, tuple[str | None, float]] = {}


def _ai_cache_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _sanitize_generic(raw: str) -> str | None:
    """Pull a single plausible generic token out of an AI reply.

    The prompt asks for one lowercase word; this defends against model chattiness
    or a refusal by taking the first alpha run and rejecting non-answers.
    """
    match = re.search(r"[A-Za-z][A-Za-z\-]*", raw)
    if not match:
        return None
    token = match.group(0).lower()
    if token in {"unknown", "none", "na", "n", "no", "not", "unsure", "null"}:
        return None
    if len(token) < 3 or len(token) > 40:
        return None
    return token


async def _ai_generic_name(db, name: str) -> str | None:
    """Ask the configured AI for the active ingredient of ``name``.

    Returns a sanitized single token, or None if the AI is unavailable or unsure.
    Uses the household's provider failover chain, so it works on Ollama-only boxes.
    """
    if not get_settings().DRUG_GENERIC_AI_FALLBACK:
        return None
    if db is None:
        # No session (e.g. unit tests) — can't build an AIService, so skip the
        # AI step and let the heuristic tail handle it.
        return None
    try:
        from app.services.ai import AIService
    except Exception:  # noqa: BLE001 — AI is optional for drug lookups
        return None
    prompt = (
        "You map medicine names to their single generic active ingredient. "
        f'Medicine: "{name}". '
        "Reply with ONLY the lowercase generic (active ingredient) name and "
        "nothing else — no punctuation, no explanation. If you are not "
        "confident, reply exactly: unknown"
    )
    try:
        text, _provider = await AIService(db)._call_ai(prompt, context="")
    except Exception:  # noqa: BLE001 — never let an AI failure break a drug lookup
        return None
    return _sanitize_generic(text or "")


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
        """Prescribing label for a single med (local catalog, else openFDA)."""
        # Local catalog first — brand-keyed, richer and accurate for Indian brands.
        if self.db is not None:
            try:
                row = await local_catalog.find(self.db, medicine_name)
            except Exception:  # noqa: BLE001
                row = None
            if row:
                return self._local_label(row)
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
        """Adverse reactions for a single med (local catalog, else openFAERS)."""
        if self.db is not None:
            try:
                row = await local_catalog.find(self.db, medicine_name)
            except Exception:  # noqa: BLE001
                row = None
            if row and row.side_effect:
                return self._local_adverse_events(row)
        generic = await self._resolve_generic(medicine_name)
        if not generic:
            return []
        client = await get_drug_info_client()
        try:
            return await openfda.adverse_events(client, generic)
        except Exception:  # noqa: BLE001
            logger.warning("openFDA adverse events failed for %r", medicine_name, exc_info=True)
            return []

    # ── ABDM Drug Registry (India) ─────────────────────────────────────

    async def substitutes(self, medicine_name: str) -> list[dict]:
        """Alternate/substitute brands (ABDM) for a single med, or []."""
        if not medicine_name or not medicine_name.strip() or not abdm.is_configured():
            return []
        client = await get_drug_info_client()
        try:
            hit = await abdm.resolve(client, medicine_name)
            if not hit or not hit.get("brand_id"):
                return []
            detail = await abdm.brand_detail(client, hit["brand_id"])
            return detail.get("substitutes", []) if detail else []
        except Exception:  # noqa: BLE001 — never break a med-detail view
            logger.warning("ABDM substitutes failed for %r", medicine_name, exc_info=True)
            return []

    async def indication(self, medicine_name: str) -> dict | None:
        """Indication/contraindication for a single med (local catalog, else ABDM)."""
        if not medicine_name or not medicine_name.strip():
            return None
        # Local catalog first.
        if self.db is not None:
            try:
                row = await local_catalog.find(self.db, medicine_name)
            except Exception:  # noqa: BLE001
                row = None
            if row:
                return self._local_indication(row)
        if not abdm.is_configured():
            return None
        client = await get_drug_info_client()
        try:
            hit = await abdm.resolve(client, medicine_name)
            if not hit:
                return None
            # Brand detail carries dose form + route; fall back to generic detail.
            if hit.get("brand_id"):
                detail = await abdm.brand_detail(client, hit["brand_id"])
            elif hit.get("generic_id"):
                detail = await abdm.generic_detail(client, hit["generic_id"])
            else:
                detail = None
            if not detail:
                return None
            return {
                "indication": detail.get("indication", ""),
                "contraindication": detail.get("contraindication", ""),
                "dose_form": detail.get("dose_form", ""),
                "routes": detail.get("routes", []),
                "source": "abdm",
            }
        except Exception:  # noqa: BLE001
            logger.warning("ABDM indication failed for %r", medicine_name, exc_info=True)
            return None

    # ── local-catalog shaping helpers ──────────────────────────────────

    def _local_label(self, row: "LocalDrug") -> dict:  # noqa: F821
        """Shape a catalog row into the openFDA-label return form."""
        sections: dict[str, str] = {}
        usage = " ".join(p for p in [row.introduction, row.benefits] if p).strip()
        if usage:
            sections["indications_and_usage"] = usage
        if row.safety_advise:
            sections["warnings_and_precautions"] = row.safety_advise
        if row.how_to_use:
            sections["dosage_and_administration"] = row.how_to_use
        if row.side_effect:
            sections["adverse_reactions"] = row.side_effect
        if row.drug_drug_interaction:
            sections["drug_interactions"] = row.drug_drug_interaction
        names = ingredient_names(row.composition or "")
        return {
            "generic_name": ", ".join(names) or None,
            "brand_name": row.product_name,
            "drug_class": row.primary_use,
            "sections": sections,
            "source": "local",
        }

    def _local_indication(self, row: "LocalDrug") -> dict:  # noqa: F821
        """Shape a catalog row into the ABDM-indication return form."""
        indication = " ".join(p for p in [row.introduction, row.benefits] if p).strip()
        contra = " ".join(
            p for p in [
                row.pregnancy_interaction,
                row.liver_interaction,
                row.kidney_interaction,
                row.safety_advise,
            ]
            if p
        ).strip()
        return {
            "indication": indication,
            "contraindication": contra,
            "dose_form": row.product_form or "",
            "routes": [],
            "source": "local",
        }

    def _local_adverse_events(self, row: "LocalDrug") -> list[dict]:  # noqa: F821
        """Split the local side-effect prose into reaction terms (no FAERS counts)."""
        seen: set[str] = set()
        out: list[dict] = []
        for term in re.split(r"[;,\n]|\.\s+", row.side_effect or ""):
            term = term.strip().strip(".,;:")
            key = term.lower()
            if not term or key in seen:
                continue
            seen.add(key)
            out.append({"term": term, "count": 0})
            if len(out) >= 12:
                break
        return out

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
        """Generic ingredient name for ``name``, or None if unresolvable.

        Resolution order: ABDM (when configured — authoritative for Indian
        brands) → RxNorm → AI brand→generic (cached, openFDA-validated) →
        strength-stripping heuristic. ABDM covers names the US sources miss
        (common for Indian brands, e.g. Ropark → ropinirole); keyless boxes
        skip straight to RxNorm unchanged.
        """
        if not name or not name.strip():
            return None
        if client is None:
            client = await get_drug_info_client()
        # Local catalog first — authoritative brand→ingredient for curated
        # Indian brands (and keeps combination drugs' primary ingredient).
        if self.db is not None:
            try:
                local = await local_catalog.resolve(self.db, name)
                if local and local.get("name"):
                    return local["name"]
            except Exception:  # noqa: BLE001 — fall through to ABDM/RxNorm/AI
                logger.debug("Local catalog resolve failed for %r; falling through", name)
        # ABDM first when configured — it knows Indian brands RxNorm doesn't.
        if abdm.is_configured():
            try:
                hit = await abdm.resolve(client, name)
                if hit and hit.get("generic_name"):
                    return hit["generic_name"]
            except Exception:  # noqa: BLE001 — fall through to RxNorm / AI
                logger.debug("ABDM resolve failed for %r; falling through", name)
        try:
            resolved = await rxnorm.resolve(client, name)
            if resolved and resolved.get("name"):
                return resolved["name"]
        except Exception:  # noqa: BLE001 — fall through to AI / heuristic
            logger.debug("RxNorm resolve failed for %r; trying AI/heuristic", name)

        # RxNorm missed → AI brand→generic fallback (cached), validated against
        # openFDA so a hallucinated name can't poison downstream lookups.
        key = _ai_cache_key(name)
        now = time.monotonic()
        cached = _generic_ai_cache.get(key)
        ttl = _GENERIC_AI_POS_TTL if (cached and cached[0]) else _GENERIC_AI_NEG_TTL
        if cached is None or now - cached[1] >= ttl:
            generic = await self._ai_resolve(name, client)
            _generic_ai_cache[key] = (generic, now)
        else:
            generic = cached[0]
        if generic:
            return generic
        return _heuristic_generic(name)

    async def _ai_resolve(self, name: str, client) -> str | None:
        """AI brand→generic, verified against openFDA's known brands. None if unverified.

        The AI can hallucinate a *real* but *wrong* drug (e.g. "Parktidine" →
        "ranitidine" — fooled by the ``-tidine`` suffix), which a bare existence
        check would accept. So we require the input name to actually appear among
        the proposed generic's known brand names (or be the generic itself); an
        unverifiable guess is rejected (→ no data) rather than shown as the wrong
        drug.
        """
        candidate = await _ai_generic_name(self.db, name)
        if not candidate:
            return None
        try:
            brands, generics = await openfda.brands_for_generic(client, candidate)
        except Exception:  # noqa: BLE001 — treat a failed probe as unresolvable
            logger.debug("openFDA brand check failed for AI generic %r", candidate)
            return None
        if not brands and not generics:
            return None  # generic not in openFDA → reject
        # Strip dosage/form from the input (e.g. "Ropark 1mg" -> "ropark") so it
        # can match a brand name, then require it to actually be a known brand of
        # the proposed generic (or the generic itself).
        norm = (_heuristic_generic(name) or "").strip().lower() or _ai_cache_key(name)
        known = set(brands) | set(generics)
        known.add((candidate or "").strip().lower())
        if norm in known:
            return candidate
        logger.debug(
            "AI generic %r for %r not confirmed among its brands (%d); rejecting",
            candidate, name, len(brands),
        )
        return None


def _heuristic_generic(name: str) -> str | None:
    """Best-effort generic name when RxNorm can't resolve the free text."""
    cleaned = _DOSAGE_RE.sub(" ", name).lower()
    words = [w for w in re.split(r"[,\s/]+", cleaned) if w and w not in _FORM_WORDS]
    # Strip leading/trailing punctuation and keep alphabetic tokens.
    alpha = [w.strip("().-") for w in words if w.strip("().-").isalpha()]
    if not alpha:
        return None
    return alpha[0].capitalize()
