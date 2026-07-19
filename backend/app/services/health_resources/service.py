"""HealthResourcesService — orchestrator over the free health-information providers.

Drug education chains RxNorm (name→RXCUI) → MedlinePlus Connect (patient-
friendly med page) and DailyMed (full label). Trials search ClinicalTrials.gov.
Condition-info is code-based MedlinePlus Connect (for when diagnoses carry
ICD-10/SNOMED codes). Every method degrades to empty on failure — a panel going
blank beats a 500 on a health record.
"""

from __future__ import annotations

import logging

from app.core.cache import cache
from app.services.drug_info.base import get_drug_info_client
from app.services.drug_info.providers import rxnorm
from app.services.health_resources.providers import (
    clinicaltables,
    clinicaltrials,
    dailymed,
    healthcanada,
    medlineplus,
    mhra,
)

logger = logging.getLogger(__name__)


class HealthResourcesService:
    def __init__(self, db=None):
        self.db = db

    async def drug_education(self, medicine_name: str) -> dict:
        """Patient-education + full-label links for a single medication.

        Returns ``{"medlineplus": [...], "dailymed": [...]}``. MedlinePlus
        Connect matches best on an RXCUI, so we resolve via RxNorm first.
        """
        empty = {"medlineplus": [], "dailymed": []}
        if not medicine_name or not medicine_name.strip():
            return empty
        try:
            client = await get_drug_info_client()
            rxcui = None
            try:
                resolved = await rxnorm.resolve(client, medicine_name)
                if resolved:
                    rxcui = resolved.get("rxcui")
            except Exception:
                logger.debug("rxnorm resolve failed for %r", medicine_name)
            if rxcui:
                medline = await medlineplus.connect(client, "rxnorm", rxcui)
            else:
                medline = []
            daily = await dailymed.labels(client, medicine_name)
            return {"medlineplus": medline, "dailymed": daily}
        except Exception:
            logger.warning("drug_education failed for %r", medicine_name, exc_info=True)
            return empty

    async def trials(self, condition: str, limit: int = 8) -> list[dict]:
        """Matching clinical trials for a condition."""
        if not condition or not condition.strip():
            return []
        try:
            client = await get_drug_info_client()
            return await clinicaltrials.trials(client, condition, limit)
        except Exception:
            logger.warning("trials failed for %r", condition, exc_info=True)
            return []

    async def condition_info(self, code_system: str, code: str) -> list[dict]:
        """MedlinePlus patient-education for an ICD-10/SNOMED/LOINC code."""
        try:
            client = await get_drug_info_client()
            return await medlineplus.connect(client, code_system, code)
        except Exception:
            logger.warning("condition_info failed %s/%s", code_system, code, exc_info=True)
            return []

    async def condition_lookup(self, condition: str) -> dict:
        """Free-text condition → normalized name/ICD-10 + MedlinePlus education.

        Chains clinicaltables (name→ICD-10-CM) into the existing MedlinePlus
        Connect provider (ICD-10→patient education). This is the keyless entry
        point that turns a free-text diagnosis into the coded lookups the other
        endpoints need. Result is cached 24h (conditions are stable; NLM asks
        callers to cache). Always returns a dict so the panel never 500s.
        """
        text = (condition or "").strip()
        empty = {"query": text, "name": None, "icd10_code": None, "synonyms": [], "topics": []}
        if not text:
            return empty
        key = f"condition_lookup:{text.lower()}"
        cached = await cache.get_async(key)
        if cached:
            return cached
        try:
            client = await get_drug_info_client()
            normalized = await clinicaltables.normalize_condition(client, text)
            name = (normalized or {}).get("name") or text
            icd10 = (normalized or {}).get("icd10_code")
            synonyms = (normalized or {}).get("synonyms") or []
            # Connect matches best on a code — skip when normalization found none.
            topics = await medlineplus.connect(client, "icd10", icd10) if icd10 else []
            result = {
                "query": text,
                "name": name,
                "icd10_code": icd10,
                "synonyms": synonyms,
                "topics": topics,
            }
        except Exception:
            logger.warning("condition_lookup failed for %r", text, exc_info=True)
            result = empty
        await cache.set_async(key, result, ttl=86400)
        return result

    async def canadian_product(self, din: str) -> dict | None:
        """Health Canada DPD product for an 8-digit DIN, or None.

        DPD has no name search (multi-MB dumps); this is a DIN/code lookup only.
        """
        if not din or not din.strip():
            return None
        try:
            client = await get_drug_info_client()
            return await healthcanada.lookup(client, din.strip())
        except Exception:
            logger.warning("canadian_product failed for %r", din, exc_info=True)
            return None

    async def uk_alerts(self, term: str, limit: int = 5) -> list[dict]:
        """MHRA drug-safety entries (UK) for a drug/term, via the GOV.UK search API."""
        if not term or not term.strip():
            return []
        try:
            client = await get_drug_info_client()
            return await mhra.search(client, term, limit)
        except Exception:
            logger.warning("uk_alerts failed for %r", term, exc_info=True)
            return []
