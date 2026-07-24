"""Drug-information router — openFDA-backed recalls, labels, and adverse events.

Member-scoped, free (no API key needed). Pair this with the AI/DrugBank drug-
*interaction* endpoints in ``member_drug_interactions.py`` — those answer
"do these two meds clash?", while these answer "is this med recalled?",
"what does its label say?", and "what side effects get reported?".

All endpoints degrade to empty/null on external failure so a panel never 500s.
"""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import require_member_in_household
from app.models.base import FamilyMember
from app.services.drug_info import DrugInfoService
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Drug Info"])

# Cache drug-info validation per medicine: registry content is stable, and the
# flyout re-opens often. key = normalized medicine name -> (verification, expires).
_DRUG_INFO_VALIDATE_TTL = 24 * 3600
_drug_info_validate_cache: dict[str, tuple[dict, float]] = {}


class DrugInfoValidateRequest(BaseModel):
    """Assembled flyout content to cross-check against the medicine name."""

    medicine: str
    indication: dict | None = None
    label: dict | None = None
    events: list[dict] = Field(default_factory=list)
    substitutes: list[dict] = Field(default_factory=list)


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


@router.post("/{member_id}/drug-info/validate")
async def validate_drug_info(
    payload: DrugInfoValidateRequest,
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Second-model check that the flyout content pertains to the right medicine.

    The flyout content is registry-sourced (openFDA/ABDM/FAERS); this guards the
    one real risk — a name-resolution error resolving the content to the wrong
    drug. Cached per medicine (24h). Disabled (returns null) when verification
    is off.
    """
    medicine = payload.medicine.strip()
    if not medicine:
        raise HTTPException(status_code=422, detail="medicine is required")

    if not get_settings().AI_VERIFICATION_ENABLED:
        return {"verification": None}

    cache_key = medicine.lower()
    now = time.monotonic()
    hit = _drug_info_validate_cache.get(cache_key)
    if hit and now < hit[1]:
        return {"verification": hit[0]}

    # Trim to the signal a checker needs: indication/contraindication text, label
    # section names, top adverse-event terms, substitute names.
    content: dict = {}
    if payload.indication:
        content["indication"] = payload.indication.get("indication", "")
        content["contraindication"] = payload.indication.get("contraindication", "")
    if payload.label:
        content["label_sections"] = list((payload.label.get("sections") or {}).keys())
    if payload.events:
        content["adverse_events"] = [e.get("term") for e in payload.events[:10] if e.get("term")]
    if payload.substitutes:
        content["substitutes"] = [s.get("name") for s in payload.substitutes[:12] if s.get("name")]

    if not content:
        return {"verification": None}

    from app.services.ai_service import AIService
    from app.services.verification_service import VerificationService

    try:
        verification = await VerificationService(db, AIService(db)).verify_drug_info(
            medicine, content
        )
    except Exception as exc:  # noqa: BLE001 — never break the flyout
        logger.warning("Drug-info validation failed for %r: %s", medicine, exc)
        return {"verification": None}

    _drug_info_validate_cache[cache_key] = (verification, now + _DRUG_INFO_VALIDATE_TTL)
    return {"verification": verification}
