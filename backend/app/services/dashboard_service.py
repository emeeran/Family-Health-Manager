"""Dashboard service — aggregates household-level health data for the main dashboard."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    HealthRecord,
    Vaccination,
)
from app.routers.members import _compute_health_score
from app.services.health_alert_service import HealthAlertService
from app.services.member_service import MemberService
from app.services.preventive_care_service import PreventiveCareService

logger = logging.getLogger(__name__)


class DashboardService:
    """Aggregate household-level dashboard data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_household_summary(self, household_id: UUID) -> dict:
        """Return the full household dashboard summary.

        Aggregates alerts, preventive care, medications, health scores,
        record activity, vaccinations, and risk levels for all active members.
        """
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)

        # --- 1. Alerts: top 10 undismissed ---
        alert_svc = HealthAlertService(self.db)
        alerts = await alert_svc.list_alerts(
            household_id=household_id,
            dismissed=False,
        )
        alerts_data = [
            {
                "id": str(a.id),
                "member_id": str(a.family_member_id),
                "alert_type": a.alert_type.value if hasattr(a.alert_type, "value") else a.alert_type,
                "severity": a.severity.value if hasattr(a.severity, "value") else a.severity,
                "title": a.title,
                "message": a.message,
                "test_name": a.test_name,
                "value": a.value,
                "reference": a.reference,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts[:10]
        ]

        # --- 2. Active members ---
        member_svc = MemberService(self.db)
        members = await member_svc.list_members(household_id, is_active=True)

        if not members:
            return {
                "alerts": alerts_data,
                "preventive_care": [],
                "medication_summary": {
                    "total_active_medications": 0,
                    "members_with_medications": 0,
                    "refill_reminders": [],
                },
                "scores": [],
                "record_activity": {
                    "total_last_30_days": 0,
                    "by_type": {},
                },
                "vaccination_status": {
                    "total_vaccinations": 0,
                    "overdue_count": 0,
                },
                "risk_summary": {
                    "high_risk_members": 0,
                    "moderate_risk_members": 0,
                    "low_risk_members": 0,
                },
            }

        member_ids = [m.id for m in members]
        # Ensure string IDs for queries that compare against string columns
        member_ids_str = [str(mid) for mid in member_ids]

        # --- 3. Preventive care recommendations (all members) ---
        preventive_svc = PreventiveCareService(self.db)
        all_preventive: list[dict] = []
        for member in members:
            recs = await preventive_svc.generate_recommendations(member)
            for rec in recs:
                rec["member_id"] = str(member.id)
                rec["member_name"] = f"{member.first_name} {member.last_name}"
            all_preventive.extend(recs)

        # --- 4. Medications per member ---
        total_medications = 0
        members_with_meds = 0
        refill_reminders: list[dict] = []
        member_medications: dict[str, list[dict]] = {}

        for member in members:
            meds = await member_svc.get_active_medications(member.id)
            member_medications[str(member.id)] = meds
            total_medications += len(meds)
            if meds:
                members_with_meds += 1
            # Refill reminders: medications with a duration hint
            for med in meds[:5]:
                refill_reminders.append({
                    "member_id": str(member.id),
                    "member_name": f"{member.first_name} {member.last_name}",
                    "medicine": med.get("medicine", ""),
                    "dosage": med.get("dosage", ""),
                    "duration": med.get("duration", ""),
                    "prescribed_date": med.get("prescribed_date"),
                })
        refill_reminders = refill_reminders[:5]

        # --- 5. Health scores (batch) ---
        scores: list[dict] = []
        for member in members:
            # Compute age
            age = today.year - member.date_of_birth.year - (
                (today.month, today.day)
                < (member.date_of_birth.month, member.date_of_birth.day)
            )

            # Count conditions from medical_history_summary
            conditions_count = 0
            if member.medical_history_summary:
                for part in member.medical_history_summary.split("; "):
                    if part.startswith("Conditions:"):
                        conditions_count = len(
                            [
                                x.strip()
                                for x in part.replace("Conditions:", "").split(",")
                                if x.strip()
                            ]
                        )
                        break

            # Recent records for this member (needed for score computation)
            recs_result = await self.db.execute(
                select(HealthRecord)
                .where(
                    HealthRecord.family_member_id == member.id,
                    HealthRecord.is_deleted.is_(False),
                )
                .order_by(HealthRecord.record_date.desc())
                .limit(20)
            )
            recent_records = list(recs_result.scalars().all())

            meds_list = member_medications.get(str(member.id), [])
            health_score, score_breakdown = _compute_health_score(
                member, conditions_count, meds_list, recent_records, age
            )

            # Determine risk level from score
            if health_score < 40:
                risk_level = "high"
            elif health_score <= 65:
                risk_level = "moderate"
            else:
                risk_level = "low"

            scores.append({
                "member_id": str(member.id),
                "first_name": member.first_name,
                "last_name": member.last_name,
                "health_score": health_score,
                "risk_level": risk_level,
                "score_breakdown": score_breakdown,
            })

        # --- 6. Record activity (last 30 days) ---
        activity_result = await self.db.execute(
            select(
                HealthRecord.record_type,
                func.count().label("cnt"),
            )
            .where(
                HealthRecord.family_member_id.in_(member_ids_str),
                HealthRecord.is_deleted.is_(False),
                HealthRecord.record_date >= thirty_days_ago,
            )
            .group_by(HealthRecord.record_type)
        )
        by_type: dict[str, int] = {}
        total_last_30 = 0
        for row in activity_result.all():
            rt = row[0]
            label = rt.value if hasattr(rt, "value") else str(rt)
            count = row[1]
            by_type[label] = count
            total_last_30 += count

        # --- 7. Vaccination status ---
        vacc_result = await self.db.execute(
            select(func.count()).where(
                Vaccination.family_member_id.in_(member_ids_str),
            )
        )
        total_vaccinations = vacc_result.scalar() or 0

        overdue_vacc_result = await self.db.execute(
            select(func.count()).where(
                Vaccination.family_member_id.in_(member_ids_str),
                Vaccination.booster_due_date.isnot(None),
                Vaccination.booster_due_date < today,
            )
        )
        overdue_count = overdue_vacc_result.scalar() or 0

        # --- 8. Risk summary ---
        risk_summary = {
            "high_risk_members": sum(1 for s in scores if s["risk_level"] == "high"),
            "moderate_risk_members": sum(1 for s in scores if s["risk_level"] == "moderate"),
            "low_risk_members": sum(1 for s in scores if s["risk_level"] == "low"),
        }

        return {
            "alerts": alerts_data,
            "preventive_care": all_preventive,
            "medication_summary": {
                "total_active_medications": total_medications,
                "members_with_medications": members_with_meds,
                "refill_reminders": refill_reminders,
            },
            "scores": scores,
            "record_activity": {
                "total_last_30_days": total_last_30,
                "by_type": by_type,
            },
            "vaccination_status": {
                "total_vaccinations": total_vaccinations,
                "overdue_count": overdue_count,
            },
            "risk_summary": risk_summary,
        }
