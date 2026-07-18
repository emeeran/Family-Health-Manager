"""HealthResourcesService — orchestrator over the free health-information providers.

Drug education chains RxNorm (name→RXCUI) → MedlinePlus Connect (patient-
friendly med page) and DailyMed (full label). Trials search ClinicalTrials.gov.
Condition-info is code-based MedlinePlus Connect (for when diagnoses carry
ICD-10/SNOMED codes). Every method degrades to empty on failure — a panel going
blank beats a 500 on a health record.
"""

from __future__ import annotations

import logging

from app.services.drug_info.base import get_drug_info_client
from app.services.drug_info.providers import rxnorm
from app.services.health_resources.providers import (
    clinicaltrials,
    dailymed,
    medlineplus,
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
