"""Dashboard router — household-level dashboard endpoints."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.core.utils import calculate_age
from app.models.base import (
    HealthRecord,
    Household,
    Vaccination,
)
from app.services.health_score_service import compute_health_score as _compute_health_score
from app.services.health_score_service import get_conditions_count
from app.services.dashboard_service import DashboardService
from app.services.member_service import MemberService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
async def get_dashboard_summary(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated household dashboard data.

    Includes alerts, preventive care recommendations, medication summary,
    health scores with breakdowns, record activity, vaccination status,
    and risk summary for all active members.
    """
    svc = DashboardService(db)
    return await svc.get_household_summary(household.id)


@router.get("/member-comparison")
async def get_member_comparison(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return side-by-side health metrics for all active household members.

    Includes health scores, BMI, medication counts, and record counts.
    """
    member_svc = MemberService(db)
    members = await member_svc.list_members(household.id, is_active=True)

    if not members:
        return []

    member_ids = [m.id for m in members]

    # Batch: aggregate record counts, vaccination counts, medications,
    # and recent records in a few queries instead of N+1 per member.
    counts_result, vacc_result, med_records_result, all_records_result = await asyncio.gather(
        # Record counts per member
        db.execute(
            select(
                HealthRecord.family_member_id,
                func.count().label("total_records"),
            )
            .where(
                HealthRecord.family_member_id.in_(member_ids),
                HealthRecord.is_deleted.is_(False),
            )
            .group_by(HealthRecord.family_member_id)
        ),
        # Vaccination counts per member
        db.execute(
            select(
                Vaccination.family_member_id,
                func.count().label("vaccination_count"),
            ).where(
                Vaccination.family_member_id.in_(member_ids),
            )
            .group_by(Vaccination.family_member_id)
        ),
        # All doctor_visit records for medication extraction
        db.execute(
            select(HealthRecord)
            .where(
                HealthRecord.family_member_id.in_(member_ids),
                HealthRecord.record_type == "doctor_visit",
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.record_date.desc())
        ),
        # Recent records for health score (ordered for per-member limiting)
        db.execute(
            select(HealthRecord)
            .where(
                HealthRecord.family_member_id.in_(member_ids),
                HealthRecord.is_deleted.is_(False),
            )
            .order_by(HealthRecord.family_member_id, HealthRecord.record_date.desc())
        ),
    )

    record_counts = {row[0]: row[1] for row in counts_result.all()}
    vacc_counts = {row[0]: row[1] for row in vacc_result.all()}

    # Build per-member medication lists from batched doctor_visit records
    import json as _json
    member_medications: dict[str, list[dict]] = {}
    for r in med_records_result.scalars().all():
        if not r.clinical_data:
            continue
        try:
            parsed = _json.loads(r.clinical_data)
            if not isinstance(parsed, dict) or parsed.get("_type") != "structured":
                continue
            if parsed.get("_medication_sync") is False:
                continue
            rx_list = parsed.get("prescriptions", [])
            if not isinstance(rx_list, list):
                continue
            mid = str(r.family_member_id)
            for rx in rx_list:
                med_name = rx.get("medicine", "").strip()
                if med_name:
                    member_medications.setdefault(mid, []).append(rx)
        except (_json.JSONDecodeError, ValueError):
            continue

    # Group recent records per member (keep last 20)
    member_records: dict[str, list] = {}
    for r in all_records_result.scalars().all():
        mid = str(r.family_member_id)
        if mid not in member_records:
            member_records[mid] = []
        if len(member_records[mid]) < 20:
            member_records[mid].append(r)

    # Build comparison data per member (no per-member DB queries)
    comparison = []
    for member in members:
        age = calculate_age(member.date_of_birth)

        # BMI
        bmi = None
        if member.height_cm and member.weight_kg and member.height_cm > 0:
            hm = member.height_cm / 100
            bmi = round(member.weight_kg / (hm * hm), 1)

        meds = member_medications.get(str(member.id), [])
        conditions_count = get_conditions_count(member.medical_history_summary)
        recent_records = member_records.get(str(member.id), [])

        health_score, score_breakdown = _compute_health_score(
            member, conditions_count, meds, recent_records, age
        )

        comparison.append({
            "member_id": str(member.id),
            "first_name": member.first_name,
            "last_name": member.last_name,
            "age": age,
            "gender": member.gender.value if hasattr(member.gender, "value") else member.gender,
            "bmi": bmi,
            "health_score": health_score,
            "score_breakdown": score_breakdown,
            "medication_count": len(meds),
            "total_records": record_counts.get(str(member.id), 0),
            "vaccination_count": vacc_counts.get(str(member.id), 0),
            "active_conditions_count": conditions_count,
        })

    return comparison


# ── Member-level risk assessment (on members router path) ────────────
# Registered under /members/{member_id}/risk-assessment via prefix below.
# Since the router is mounted at /api/v1/dashboard, we add a sub-router
# for the members risk endpoint. However, to keep the URL clean we
# include a separate micro-router.


risk_router = APIRouter(prefix="/members", tags=["Dashboard"])


@risk_router.get("/{member_id}/risk-assessment")
async def get_member_risk_assessment(
    member_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Return risk level and risk factors for a specific member."""
    member_svc = MemberService(db)
    try:
        member = await member_svc.get_member(household.id, member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")

    today = date.today()
    age = calculate_age(member.date_of_birth)

    # Gather data needed for health score
    meds = await member_svc.get_active_medications(member.id)

    conditions_count = get_conditions_count(member.medical_history_summary)

    recs_result = await db.execute(
        select(HealthRecord)
        .where(
            HealthRecord.family_member_id == member.id,
            HealthRecord.is_deleted.is_(False),
        )
        .order_by(HealthRecord.record_date.desc())
        .limit(20)
    )
    recent_records = list(recs_result.scalars().all())

    health_score, score_breakdown = _compute_health_score(
        member, conditions_count, meds, recent_records, age
    )

    # Determine risk level
    if health_score < 40:
        risk_level = "high"
    elif health_score <= 65:
        risk_level = "moderate"
    else:
        risk_level = "low"

    # Build risk factors from score breakdown (categories scoring below max)
    risk_factors: list[dict] = []
    for category, details in score_breakdown.items():
        score_val = details.get("score", 0)
        max_val = details.get("max", 0)
        if score_val < max_val:
            risk_factors.append({
                "category": category,
                "score": score_val,
                "max": max_val,
                "label": details.get("label", ""),
            })

    # Check for overdue vaccinations
    overdue_vacc = await db.execute(
        select(func.count()).where(
            Vaccination.family_member_id == member.id,
            Vaccination.booster_due_date.isnot(None),
            Vaccination.booster_due_date < today,
        )
    )
    overdue_vacc_count = overdue_vacc.scalar() or 0
    if overdue_vacc_count > 0:
        risk_factors.append({
            "category": "overdue_vaccinations",
            "score": 0,
            "max": overdue_vacc_count,
            "label": f"{overdue_vacc_count} overdue vaccination booster(s)",
        })

    # Check for overdue follow-ups
    overdue_followups = await db.execute(
        select(func.count()).where(
            HealthRecord.family_member_id == member.id,
            HealthRecord.is_deleted.is_(False),
            HealthRecord.next_review_date.isnot(None),
            HealthRecord.next_review_date < today,
        )
    )
    overdue_fup_count = overdue_followups.scalar() or 0
    if overdue_fup_count > 0:
        risk_factors.append({
            "category": "overdue_followups",
            "score": 0,
            "max": overdue_fup_count,
            "label": f"{overdue_fup_count} overdue follow-up(s)",
        })

    # Sort risk factors: lower relative score first (worse categories)
    risk_factors.sort(key=lambda f: f["score"] / f["max"] if f["max"] > 0 else 1)

    return {
        "member_id": str(member.id),
        "first_name": member.first_name,
        "last_name": member.last_name,
        "health_score": health_score,
        "risk_level": risk_level,
        "risk_factors": risk_factors,
        "score_breakdown": score_breakdown,
    }
