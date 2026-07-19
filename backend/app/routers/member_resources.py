"""Health-resources router — patient education, clinical trials, full drug labels.

Free, no key. Member-scoped. Complements the drug-* endpoints: those answer
"is this med safe?"; these answer "where can I learn more?".

- ``/drug-education``      — MedlinePlus patient pages + DailyMed full labels
- ``/clinical-trials``     — ClinicalTrials.gov trials for a condition
- ``/condition-info``      — MedlinePlus education for an ICD-10/SNOMED/LOINC code
- ``/canadian-product``    — Health Canada DPD product for an 8-digit DIN
- ``/uk-alerts``           — MHRA drug-safety alerts (GOV.UK) for a drug/term

All degrade to empty/null on external failure so a panel never 500s.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_member_in_household
from app.models.base import FamilyMember
from app.models.record import HealthRecord
from app.services.health_resources import HealthResourcesService

logger = logging.getLogger(__name__)

_DIN_RE = re.compile(r"^\d{8}$")

router = APIRouter(prefix="/members", tags=["Health Resources"])


@router.get("/{member_id}/drug-education")
async def get_drug_education(
    medicine: str = Query(..., description="Medication name to look up"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Patient-education + full-label links for a single medication."""
    if not medicine.strip():
        raise HTTPException(status_code=422, detail="medicine query parameter is required")
    return await HealthResourcesService(db).drug_education(medicine.strip())


@router.get("/{member_id}/clinical-trials")
async def get_clinical_trials(
    condition: str = Query(..., description="Condition to search trials for"),
    limit: int = Query(8, ge=1, le=50),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Matching clinical trials for a condition (ClinicalTrials.gov)."""
    if not condition.strip():
        raise HTTPException(status_code=422, detail="condition query parameter is required")
    trials = await HealthResourcesService(db).trials(condition.strip(), limit)
    return {"trials": trials, "condition": condition.strip()}


@router.get("/{member_id}/condition-info")
async def get_condition_info(
    code_system: str = Query(..., description="icd10 | snomed | loinc | rxnorm | ndc"),
    code: str = Query(..., description="The code to look up"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """MedlinePlus patient-education for a coded diagnosis/lab/medication."""
    if not code.strip():
        raise HTTPException(status_code=422, detail="code query parameter is required")
    results = await HealthResourcesService(db).condition_info(code_system, code.strip())
    return {"results": results}


@router.get("/{member_id}/condition-lookup")
async def get_condition_lookup(
    condition: str = Query(..., description="Condition name (free text) to look up"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Free-text condition → ICD-10 + MedlinePlus patient education.

    Normalizes the term via NIH Clinical Tables, then feeds the code to
    MedlinePlus Connect. Keyless; degrades to an empty result on failure.
    """
    if not condition.strip():
        raise HTTPException(status_code=422, detail="condition query parameter is required")
    return await HealthResourcesService(db).condition_lookup(condition.strip())


@router.get("/{member_id}/conditions")
async def get_member_conditions(
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Distinct condition/diagnosis strings drawn from the member's records."""
    result = await db.execute(
        select(HealthRecord.diagnosis)
        .where(
            HealthRecord.family_member_id == member.id,
            HealthRecord.is_deleted.is_(False),
            HealthRecord.diagnosis.is_not(None),
        )
        .distinct()
    )
    conditions = [d.strip() for d in result.scalars() if d and d.strip()]
    return {"conditions": conditions}


@router.get("/{member_id}/canadian-product")
async def get_canadian_product(
    din: str = Query(..., description="8-digit Canadian Drug Identification Number"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Health Canada DPD product for a DIN (no name search available)."""
    din_clean = din.strip()
    if not _DIN_RE.match(din_clean):
        raise HTTPException(status_code=422, detail="DIN must be exactly 8 digits")
    product = await HealthResourcesService(db).canadian_product(din_clean)
    return {"product": product}


@router.get("/{member_id}/uk-alerts")
async def get_uk_alerts(
    term: str = Query(..., description="Drug name or term to search MHRA alerts for"),
    limit: int = Query(5, ge=1, le=20),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """MHRA drug-safety alerts/news (GOV.UK) for a drug or term — UK recall source."""
    if not term.strip():
        raise HTTPException(status_code=422, detail="term query parameter is required")
    alerts = await HealthResourcesService(db).uk_alerts(term.strip(), limit)
    return {"alerts": alerts, "term": term.strip()}
