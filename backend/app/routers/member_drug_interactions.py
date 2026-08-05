"""Drug interaction checking router — AI-powered medication interaction analysis."""

import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.models.ai import AIInsight
from app.models.base import Household
from app.services.drug_info import DrugInfoService
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Drug Interactions"])


async def _generate_interactions(
    db: AsyncSession, household: Household, medications: list[dict], cloud_consent: bool = True
) -> list[dict]:
    """DrugBank-first, AI-fallback interactions, each tagged with ``source``.

    DrugBank (authoritative, when a key is configured) is tried first. If it
    yields nothing — no key, meds unresolvable, or genuinely no interactions —
    we fall back to the existing AI checker so behavior is unchanged for
    Ollama-only installs. Every returned interaction carries ``source`` =
    ``"drugbank"`` or ``"ai"`` so the UI can badge it. ``cloud_consent=False``
    forces the AI fallback local-only (Ollama).
    """
    interactions = await DrugInfoService(db).ddi(medications)

    if not interactions:
        from app.services.ai_service import AIService

        try:
            ai_service = AIService(db, household_id=household.id).set_cloud_consent(cloud_consent)
            interactions = await ai_service.check_drug_interactions(medications)
        except Exception as exc:
            logger.error("Drug interaction check failed: %s", exc)
            interactions = []

    for ix in interactions:
        if isinstance(ix, dict) and not ix.get("source"):
            ix["source"] = "ai"
    return interactions


def _insight_verification_dict(insight: AIInsight) -> dict:
    """Build the verification sub-object from an AIInsight's verification fields."""
    return {
        "status": insight.verification_status,
        "claims_checked": insight.verification_claims_checked,
        "verifier_provider": insight.verification_verifier,
        "summary": insight.verification_summary,
        "warnings": json.loads(insight.verification_warnings_json)
        if insight.verification_warnings_json
        else None,
        "verified_at": insight.verification_at.isoformat() if insight.verification_at else None,
    }


async def _verify_ddi_inline(
    db: AsyncSession,
    household: Household,
    insight: AIInsight,
    interactions: list[dict],
    medications: list[dict],
    cloud_consent: bool = True,
) -> dict | None:
    """Synchronously validate AI-generated drug interactions with a second model.

    Writes the result onto ``insight`` (the cached AIInsight) and returns the
    verification dict. Returns None when verification is disabled or the result
    was DrugBank-sourced (authoritative — no AI content to validate). DDI is
    non-streaming and cached, so the check always runs inline regardless of
    ``AI_VERIFICATION_SYNCHRONOUS``.
    """
    from app.core.config import get_settings

    if not get_settings().AI_VERIFICATION_ENABLED:
        return None
    if not any(isinstance(ix, dict) and ix.get("source") == "ai" for ix in interactions):
        return None  # DrugBank-only — authoritative, nothing AI-generated to check.

    from app.services.ai_service import AIService
    from app.services.verification_service import DDI_VERIFICATION_PROMPT, VerificationService

    med_list = "; ".join(
        f"{m.get('medicine', '?')} ({m.get('dosage', '?')})" for m in medications
    )
    prompt = DDI_VERIFICATION_PROMPT.format(
        medications=med_list[:2000], interactions=insight.response
    )
    try:
        await VerificationService(
            db, AIService(db, household_id=household.id).set_cloud_consent(cloud_consent)
        ).verify_insight(insight, prompt=prompt)
        await db.flush()
    except Exception as exc:
        logger.warning("DDI verification failed: %s", exc)
    return _insight_verification_dict(insight)


async def _generate_cache_and_verify(
    db: AsyncSession,
    household: Household,
    member_id: UUID,
    medications: list[dict],
    cloud_consent: bool = True,
) -> dict:
    """Generate interactions, cache as an AIInsight, validate inline, commit."""
    interactions = await _generate_interactions(db, household, medications, cloud_consent)
    cached_insight = AIInsight(
        prompt=f"__drug_interactions__{member_id}",
        response=json.dumps(interactions),
        provider_used="auto",
    )
    db.add(cached_insight)
    await db.flush()

    verification = await _verify_ddi_inline(
        db, household, cached_insight, interactions, medications, cloud_consent
    )
    try:
        await db.commit()
    except Exception as exc:
        logger.error("Failed to cache drug interactions: %s", exc)

    return {
        "interactions": interactions,
        "medications_checked": len(medications),
        "cached_at": None,
        "verification": verification,
    }


@router.get("/{member_id}/latest-drug-interactions")
async def get_latest_drug_interactions(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return cached drug interactions, or auto-generate if none/stale (>24h)."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medications = await service.get_active_medications(member_id)
    if len(medications) < 2:
        return {"interactions": [], "medications_checked": len(medications)}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cache_key = f"__drug_interactions__{member_id}"
    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.prompt == cache_key,
            AIInsight.generated_at >= cutoff,
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    cached = result.scalar_one_or_none()

    if cached:
        try:
            interactions = json.loads(cached.response)
            if isinstance(interactions, list):
                return {
                    "interactions": interactions,
                    "medications_checked": len(medications),
                    "cached_at": cached.generated_at.isoformat(),
                    "verification": _insight_verification_dict(cached),
                }
        except (json.JSONDecodeError, ValueError):
            pass

    cloud_consent = await MemberService(db).get_cloud_consent(member_id)
    return await _generate_cache_and_verify(db, household, member_id, medications, cloud_consent)


@router.get("/{member_id}/duplicate-therapy")
async def get_duplicate_therapy(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Flag potential same-therapeutic-class medication overlap (clinician review).

    Purely deterministic (curated class map) — no AI call. Returns classes where
    the member is on ≥2 active meds from the same class (e.g. two statins, two
    NSAIDs, ACE inhibitor + ARB). These are POTENTIAL duplicates for review, not
    certain errors.
    """
    from app.services.duplicate_therapy_service import detect_duplicate_therapy

    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medications = await service.get_active_medications(member_id)
    findings = detect_duplicate_therapy(medications)
    return {
        "findings": [f.to_dict() for f in findings],
        "medications_checked": len(medications),
    }


@router.get("/{member_id}/drug-interactions")
async def get_drug_interactions(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Check drug interactions between active medications (DrugBank → AI)."""
    service = MemberService(db)
    try:
        await service.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    medications = await service.get_active_medications(member_id)

    if len(medications) < 2:
        return {"interactions": [], "medications_checked": len(medications)}

    cloud_consent = await MemberService(db).get_cloud_consent(member_id)
    return await _generate_cache_and_verify(db, household, member_id, medications, cloud_consent)
