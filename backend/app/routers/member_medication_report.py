"""Medication Report router — generate a comprehensive report across a member's
current medication regimen (active meds + drug-drug interactions + FDA safety
signals), streamed over SSE.

Mirrors the Smart Report router (``member_smart_report.py``): the report is an
``AIInsight`` row persisted under a ``__medreport__{member_id}__`` prompt prefix
so it can be retrieved later via ``GET .../latest``.
"""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token, require_member_in_household
from app.core.sse import make_sse_stream
from app.models.ai import AIInsight
from app.models.base import Household, FamilyMember
from app.prompts.insight_prompts import MEDICATION_REPORT_PROMPT
from app.schemas.insight_serializers import serialize_medication_report_payload
from app.services.drug_info import DrugInfoService
from app.services.medication_service import MedicationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["Medication Report"])


def _fmt_meds(meds: list[dict]) -> str:
    lines = []
    for i, m in enumerate(meds, 1):
        parts = [f"{i}. {m.get('medicine', '?')}"]
        if m.get("type"):
            parts.append(f"({m['type']})")
        sched = ", ".join(
            str(m[k])
            for k in ("dosage", "timing", "duration")
            if m.get(k)
        )
        if sched:
            parts.append(f"— {sched}")
        if m.get("start_date"):
            window = m["start_date"]
            if m.get("end_date"):
                window = f"{window} to {m['end_date']}"
            parts.append(f"({window})")
        if m.get("note"):
            parts.append(f"note: {m['note']}")
        if m.get("provider_name"):
            parts.append(f"Rx by {m['provider_name']}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _fmt_interactions(interactions: list[dict]) -> str:
    if not interactions:
        return "None reported (or interaction source not configured)."
    lines = []
    for it in interactions:
        desc = (
            it.get("description")
            or it.get("summary")
            or it.get("statement")
            or json.dumps(it)[:200]
        )
        severity = it.get("severity") or it.get("risk") or "unknown"
        pair = it.get("pair") or it.get("drugs") or it.get("medications")
        label = f"{pair} " if pair else ""
        lines.append(f"- {label}({severity}): {desc}")
    return "\n".join(lines)


def _fmt_recalls(recalls: list[dict]) -> str:
    if not recalls:
        return "No active recalls."
    lines = []
    for r in recalls[:20]:  # cap to keep the prompt bounded
        reason = r.get("reason_for_recall") or r.get("reason") or "unspecified"
        product = r.get("product_description") or r.get("product") or ""
        matched = ", ".join(r.get("matched_medications", []) or [])
        lines.append(f"- [{matched}] {reason} — {product}".rstrip(" —"))
    return "\n".join(lines)


async def _build_medication_context(member_id: UUID, db: AsyncSession) -> str:
    """Assemble the grounding context: active meds + DDI + recalls."""
    meds = await MedicationService(db).get_active_medications(member_id)
    if not meds:
        return "ACTIVE MEDICATIONS: none recorded."

    drug_info = DrugInfoService(db)
    interactions = await drug_info.ddi(meds)
    recalls = await drug_info.recalls(meds)

    return (
        f"ACTIVE MEDICATIONS ({len(meds)}):\n{_fmt_meds(meds)}\n\n"
        f"DRUG-DRUG INTERACTIONS:\n{_fmt_interactions(interactions)}\n\n"
        f"FDA SAFETY / RECALLS:\n{_fmt_recalls(recalls)}"
    )


def _med_postprocess(full_response: str, insight: AIInsight) -> dict:
    """Enrich the ``complete`` frame with the persisted medication-report payload."""
    payload = serialize_medication_report_payload(insight)
    return {
        "id": str(insight.id),
        "generated_at": insight.generated_at.isoformat(),
        "report": payload,
    }


async def _build_prompt(member_id: UUID, db: AsyncSession) -> str:
    context = await _build_medication_context(member_id, db)
    return f"__medreport__{member_id}__\n\n{MEDICATION_REPORT_PROMPT}\n\n--- Context ---\n{context}"


@router.post("/{member_id}/medication-report/stream")
async def generate_medication_report_stream(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Stream a comprehensive medication-regimen report (SSE)."""
    from app.services.ai_service import AIService

    try:
        prompt = await _build_prompt(member_id, db)
    except Exception as exc:
        logger.error("Medication report context build failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not load medication data.")

    ai_service = AIService(db, household_id=household.id)
    return make_sse_stream(
        ai_service.generate_insight_stream(
            prompt=prompt,
            postprocess=_med_postprocess,
        ),
        db,
        request,
    )


@router.get("/{member_id}/medication-report/latest")
async def get_latest_medication_report(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    member: FamilyMember = Depends(require_member_in_household),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest persisted Medication Report, or null."""
    result = await db.execute(
        select(AIInsight)
        .where(
            AIInsight.prompt.like(f"__medreport__{member_id}__%"),
            AIInsight.health_record_id.is_(None),
        )
        .order_by(AIInsight.generated_at.desc())
        .limit(1)
    )
    insight = result.scalar_one_or_none()
    if not insight:
        return {"report": None}
    return {"report": serialize_medication_report_payload(insight)}
