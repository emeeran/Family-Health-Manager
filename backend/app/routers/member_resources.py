"""Health-resources router — patient education, clinical trials, full drug labels.

Free, no key. Member-scoped. Complements the drug-* endpoints: those answer
"is this med safe?"; these answer "where can I learn more?".

- ``/drug-education``      — MedlinePlus patient pages + DailyMed full labels
- ``/clinical-trials``     — ClinicalTrials.gov trials for a condition
- ``/condition-info``      — MedlinePlus education for an ICD-10/SNOMED/LOINC code

All degrade to empty/null on external failure so a panel never 500s.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_member_in_household
from app.models.base import FamilyMember
from app.services.health_resources import HealthResourcesService

logger = logging.getLogger(__name__)

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
