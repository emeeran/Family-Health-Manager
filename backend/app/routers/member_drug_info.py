"""Drug-information router — openFDA-backed recalls, labels, and adverse events.

Member-scoped, free (no API key needed). Pair this with the AI/DrugBank drug-
*interaction* endpoints in ``member_drug_interactions.py`` — those answer
"do these two meds clash?", while these answer "is this med recalled?",
"what does its label say?", and "what side effects get reported?".

All endpoints degrade to empty/null on external failure so a panel never 500s.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_member_in_household
from app.models.base import FamilyMember
from app.services.drug_info import DrugInfoService
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Drug Info"])


async def _active_medications(db: AsyncSession, member_id) -> list[dict]:
    return await MemberService(db).get_active_medications(member_id)


@router.get("/{member_id}/drug-recalls")
async def get_drug_recalls(
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """FDA recall (enforcement) reports matching any of the member's active meds."""
    medications = await _active_medications(db, member.id)
    service = DrugInfoService(db)
    recalls = await service.recalls(medications)
    return {
        "recalls": recalls,
        "medications_checked": len(medications),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/{member_id}/drug-label")
async def get_drug_label(
    medicine: str = Query(..., description="Medication name to look up"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """FDA prescribing label (key sections) for a single medication."""
    if not medicine.strip():
        raise HTTPException(status_code=422, detail="medicine query parameter is required")
    label = await DrugInfoService(db).label(medicine.strip())
    return {"label": label}


@router.get("/{member_id}/drug-adverse-events")
async def get_drug_adverse_events(
    medicine: str = Query(..., description="Medication name to look up"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Top reported adverse reactions (FAERS) for a single medication."""
    if not medicine.strip():
        raise HTTPException(status_code=422, detail="medicine query parameter is required")
    events = await DrugInfoService(db).adverse_events(medicine.strip())
    return {"events": events}


@router.get("/{member_id}/drug-substitutes")
async def get_drug_substitutes(
    medicine: str = Query(..., description="Medication name to look up"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Alternate/substitute brands (ABDM Drug Registry, India) for a medication.

    Returns an empty list when ABDM is unconfigured or no match is found.
    """
    if not medicine.strip():
        raise HTTPException(status_code=422, detail="medicine query parameter is required")
    substitutes = await DrugInfoService(db).substitutes(medicine.strip())
    return {"substitutes": substitutes}


@router.get("/{member_id}/drug-indication")
async def get_drug_indication(
    medicine: str = Query(..., description="Medication name to look up"),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Indian-context indication/contraindication (ABDM) for a medication.

    Returns ``{"indication": null}`` when ABDM is unconfigured or no match found.
    """
    if not medicine.strip():
        raise HTTPException(status_code=422, detail="medicine query parameter is required")
    indication = await DrugInfoService(db).indication(medicine.strip())
    return {"indication": indication}
