"""Dashboard service — aggregates household-level health data for the main dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone as _tz
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import calculate_age
from app.models.base import (
    Conversation,
    FamilyMember,
    HealthRecord,
    Household,
    Notification,
    Provider,
    Reminder,
    Vaccination,
)
from app.services.health_score_service import compute_health_score as _compute_health_score
from app.services.health_score_service import get_conditions_count
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
        Queries are parallelized where possible using asyncio.gather.
        """
        today = date.today()
        thirty_days_ago = today - timedelta(days=30)

        # --- Phase 1: Alerts + Members (parallel) ---
        alert_svc = HealthAlertService(self.db)
        member_svc = MemberService(self.db)

        alerts, members = await asyncio.gather(
            alert_svc.list_alerts(household_id=household_id, dismissed=False),
            member_svc.list_members(household_id, is_active=True),
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
        now_utc = datetime.now(_tz.utc)
        records_per_member_limit = 20
        batch_limit = len(member_ids) * records_per_member_limit

        # --- Phase 2: Batch DB queries (all parallel) ---
        (
            med_result,
            batch_records_result,
            activity_result,
            vacc_result,
            overdue_vacc_result,
            providers_result,
            notif_result,
            rem_result,
            recent_result,
            hh_result,
            conv_result,
        ) = await asyncio.gather(
            # 3. Doctor visit records for medications
            self.db.execute(
                select(HealthRecord)
                .where(
                    HealthRecord.family_member_id.in_(member_ids),
                    HealthRecord.record_type == "doctor_visit",
                    HealthRecord.is_deleted.is_(False),
                )
                .order_by(HealthRecord.record_date.desc())
            ),
            # 4. Recent records per member (bounded limit)
            self.db.execute(
                select(HealthRecord)
                .where(
                    HealthRecord.family_member_id.in_(member_ids),
                    HealthRecord.is_deleted.is_(False),
                )
                .order_by(HealthRecord.family_member_id, HealthRecord.record_date.desc())
                .limit(batch_limit)
            ),
            # 6. Record activity (last 30 days)
            self.db.execute(
                select(
                    HealthRecord.record_type,
                    func.count().label("cnt"),
                )
                .where(
                    HealthRecord.family_member_id.in_(member_ids),
                    HealthRecord.is_deleted.is_(False),
                    HealthRecord.record_date >= thirty_days_ago,
                )
                .group_by(HealthRecord.record_type)
            ),
            # 7a. Total vaccinations
            self.db.execute(
                select(func.count()).where(
                    Vaccination.family_member_id.in_(member_ids),
                )
            ),
            # 7b. Overdue vaccinations
            self.db.execute(
                select(func.count()).where(
                    Vaccination.family_member_id.in_(member_ids),
                    Vaccination.booster_due_date.isnot(None),
                    Vaccination.booster_due_date < today,
                )
            ),
            # 11. Providers count
            self.db.execute(
                select(func.count()).select_from(Provider).where(
                    Provider.household_id == household_id,
                )
            ),
            # 12. Unread notifications
            self.db.execute(
                select(func.count()).select_from(Notification).where(
                    Notification.household_id == household_id,
                    Notification.is_read.is_(False),
                )
            ),
            # 13. Upcoming reminders
            self.db.execute(
                select(Reminder)
                .where(
                    Reminder.household_id == household_id,
                    Reminder.is_active.is_(True),
                    Reminder.start_datetime >= now_utc,
                )
                .order_by(Reminder.start_datetime.asc())
                .limit(5)
            ),
            # 14. Recent records (last 30)
            self.db.execute(
                select(HealthRecord)
                .where(
                    HealthRecord.family_member_id.in_(member_ids),
                    HealthRecord.is_deleted.is_(False),
                )
                .order_by(HealthRecord.created_at.desc())
                .limit(30)
            ),
            # 15. Household name
            self.db.execute(
                select(Household).where(Household.id == household_id)
            ),
            # 16. Conversations count
            self.db.execute(
                select(func.count()).select_from(Conversation).where(
                    Conversation.household_id == household_id,
                )
            ),
        )

        # --- Phase 3: Process batch query results ---

        # 3. Build per-member medication lists
        member_medications: dict[str, list[dict]] = {str(mid): [] for mid in member_ids}
        for r in med_result.scalars().all():
            if not r.clinical_data:
                continue
            try:
                parsed = json.loads(r.clinical_data)
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
                        member_medications.setdefault(mid, []).append({
                            "medicine": med_name,
                            "dosage": rx.get("dosage", ""),
                            "duration": rx.get("duration", ""),
                            "prescribed_date": r.record_date.isoformat() if r.record_date else None,
                        })
            except (json.JSONDecodeError, ValueError):
                continue

        total_medications = sum(len(v) for v in member_medications.values())
        members_with_meds = sum(1 for v in member_medications.values() if v)
        refill_reminders: list[dict] = []
        for member in members:
            meds = member_medications.get(str(member.id), [])
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

        # 4. Group records by member (keep last N per member)
        member_records: dict[str, list] = {}
        for r in batch_records_result.scalars().all():
            mid = str(r.family_member_id)
            if mid not in member_records:
                member_records[mid] = []
            if len(member_records[mid]) < records_per_member_limit:
                member_records[mid].append(r)

        # 5. Preventive care (parallel per member)
        preventive_svc = PreventiveCareService(self.db)

        async def _member_preventive(m: FamilyMember) -> list[dict]:
            recs = await preventive_svc.generate_recommendations(m)
            for rec in recs:
                rec["member_id"] = str(m.id)
                rec["member_name"] = f"{m.first_name} {m.last_name}"
            return recs

        all_preventive_results = await asyncio.gather(
            *[_member_preventive(m) for m in members]
        )
        all_preventive: list[dict] = []
        for recs in all_preventive_results:
            all_preventive.extend(recs)

        # Health scores
        scores: list[dict] = []
        for member in members:
            age = calculate_age(member.date_of_birth)
            conditions_count = get_conditions_count(member.medical_history_summary)
            recent_recs = member_records.get(str(member.id), [])
            meds_list = member_medications.get(str(member.id), [])
            health_score, score_breakdown = _compute_health_score(
                member, conditions_count, meds_list, recent_recs, age
            )

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

        # 6. Record activity
        by_type: dict[str, int] = {}
        total_last_30 = 0
        for row in activity_result.all():
            rt = row[0]
            label = rt.value if hasattr(rt, "value") else str(rt)
            count = row[1]
            by_type[label] = count
            total_last_30 += count

        # 7. Vaccination status
        total_vaccinations = vacc_result.scalar() or 0
        overdue_count = overdue_vacc_result.scalar() or 0

        # 9. Risk summary
        risk_summary = {
            "high_risk_members": sum(1 for s in scores if s["risk_level"] == "high"),
            "moderate_risk_members": sum(1 for s in scores if s["risk_level"] == "moderate"),
            "low_risk_members": sum(1 for s in scores if s["risk_level"] == "low"),
        }

        # 10. Members list
        members_data = [
            {
                "id": str(m.id),
                "first_name": m.first_name,
                "last_name": m.last_name,
                "date_of_birth": m.date_of_birth.isoformat(),
                "gender": m.gender.value if hasattr(m.gender, "value") else m.gender,
                "relationship": m.relationship_type.value if hasattr(m.relationship_type, "value") else m.relationship_type,
                "blood_group": m.blood_group,
                "bmi": m.weight_kg and m.height_cm and m.height_cm > 0
                    and round(m.weight_kg / (m.height_cm / 100) ** 2, 1) or None,
                "is_active": m.is_active,
                "allergies": json.loads(m.allergies_json) if m.allergies_json else None,
            }
            for m in members
        ]

        # 11-16. Scalar + list results
        providers_count = providers_result.scalar() or 0
        unread_notifications = notif_result.scalar() or 0
        upcoming_reminders = [
            {
                "id": str(r.id),
                "title": r.title,
                "start_datetime": r.start_datetime.isoformat() if r.start_datetime else None,
                "reminder_type": r.reminder_type.value if hasattr(r.reminder_type, "value") else r.reminder_type,
            }
            for r in rem_result.scalars().all()
        ]
        recent_records = []
        for r in recent_result.scalars().all():
            clinical_preview = None
            if r.clinical_data:
                try:
                    parsed = json.loads(r.clinical_data)
                    preview = {}
                    if parsed.get("chief_complaint"):
                        preview["chief_complaint"] = parsed["chief_complaint"]
                    if parsed.get("glucose_value"):
                        preview["glucose_value"] = parsed["glucose_value"]
                    if parsed.get("hba1c_value"):
                        preview["hba1c_value"] = parsed["hba1c_value"]
                    if isinstance(parsed.get("lab_results"), list) and parsed["lab_results"]:
                        preview["lab_results"] = [
                            {"test_name": t.get("test_name")}
                            for t in parsed["lab_results"][:2]
                        ]
                        preview["lab_results_count"] = len(parsed["lab_results"])
                    if preview:
                        clinical_preview = json.dumps(preview)
                except (json.JSONDecodeError, ValueError):
                    # For unstructured text, send first 60 chars
                    first_line = r.clinical_data.split("\n")[0]
                    clinical_preview = first_line[:60]
                    if len(first_line) > 60:
                        clinical_preview += "..."

            recent_records.append({
                "id": str(r.id),
                "family_member_id": str(r.family_member_id),
                "record_type": r.record_type.value if hasattr(r.record_type, "value") else r.record_type,
                "record_date": r.record_date.isoformat() if r.record_date else None,
                "diagnosis": r.diagnosis,
                "clinical_data": clinical_preview,
                "is_deleted": r.is_deleted,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        household_obj = hh_result.scalar_one_or_none()
        household_name = household_obj.name if household_obj else "My Family"
        conversations_count = conv_result.scalar() or 0

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
            "members": members_data,
            "household_name": household_name,
            "providers_count": providers_count,
            "unread_notifications": unread_notifications,
            "upcoming_reminders": upcoming_reminders,
            "recent_records": recent_records,
            "conversations_count": conversations_count,
        }
