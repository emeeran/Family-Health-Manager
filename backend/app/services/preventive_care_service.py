"""Preventive care recommendation engine.

Generates age- and condition-appropriate health screening and vaccination
recommendations using deterministic rules (no AI — reliable, works offline).
"""
import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import HealthRecord, FamilyMember

logger = logging.getLogger(__name__)

# ── Rule definitions ────────────────────────────────────────────────
# (min_age, max_age, title, description, months_interval, priority, category)
# Keep these relevant and actionable — no filler.
AGE_BASED_RULES: list[tuple[int, int | None, str, str, int, str, str]] = [
    (18, None, "Annual Physical Exam", "General health check-up", 12, "medium", "screening"),
    (18, None, "Dental Check-up", "Oral health examination & cleaning", 12, "medium", "screening"),
    (18, None, "Blood Pressure Screening", "Check at every health visit", 12, "high", "screening"),
    (18, None, "Tetanus Booster (Td/Tdap)", "Every 10 years", 120, "medium", "vaccination"),
    (26, None, "HPV Vaccine (if unvaccinated)", "Gardasil 9 — up to age 45", 0, "medium", "vaccination"),
    (30, None, "Annual Lipid Profile", "Cholesterol & triglycerides", 12, "medium", "lab"),
    (35, None, "Thyroid Screening (TSH)", "Baseline thyroid function", 60, "medium", "lab"),
    (40, None, "Comprehensive Metabolic Panel", "Kidney & liver function", 12, "high", "lab"),
    (45, None, "Diabetes Screening (HbA1c)", "Every 3 years if non-diabetic", 36, "high", "lab"),
    (50, 75, "Colorectal Cancer Screening", "Colonoscopy or FIT test", 120, "high", "screening"),
    (55, None, "Annual Eye Examination", "Glaucoma, cataracts, retinopathy", 12, "medium", "screening"),
    (60, None, "Bone Density (DEXA)", "Osteoporosis screening", 24, "medium", "screening"),
    (65, None, "Pneumococcal Vaccine", "PCV20 or PPSV23 at age 65", 0, "high", "vaccination"),
    (65, None, "Annual Flu Vaccine", "Influenza immunization", 12, "high", "vaccination"),
    (65, None, "Shingles Vaccine (Shingrix)", "Two-dose series for adults 65+", 0, "high", "vaccination"),
]

# (condition_keyword, title, description, months_interval, priority, category)
CONDITION_RULES: list[tuple[str, str, str, int, str, str]] = [
    ("diabetes", "HbA1c Test (q3 months)", "Glycemic control monitoring", 3, "high", "lab"),
    ("diabetes", "Diabetic Eye Exam", "Retinopathy screening", 12, "high", "screening"),
    ("diabetes", "Diabetic Foot Exam", "Neuropathy & ulcer check", 12, "high", "screening"),
    ("diabetes", "Kidney Function (uACR + eGFR)", "Diabetic nephropathy screening", 12, "high", "lab"),
    ("hypertension", "Kidney Function Test", "Serum creatinine & eGFR", 12, "high", "lab"),
    ("hypertension", "Quarterly BP Check", "Treatment efficacy monitoring", 3, "high", "screening"),
    ("cholesterol", "Lipid Profile (q6 months)", "Treatment response monitoring", 6, "high", "lab"),
    ("thyroid", "Thyroid Function (TSH/T3/T4)", "Thyroid disorder monitoring", 12, "high", "lab"),
    ("depression", "Mental Health Follow-up", "Assessment & medication review", 3, "high", "screening"),
    ("asthma", "Pulmonary Function Test", "Spirometry monitoring", 12, "medium", "lab"),
]

# Max days overdue before we stop showing (avoids stale noise)
MAX_OVERDUE_DAYS = 180


class PreventiveCareService:
    """Generate preventive care recommendations based on age, conditions, and history."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_recommendations(
        self, member: FamilyMember
    ) -> list[dict]:
        """Generate personalized preventive care recommendations."""
        today = date.today()
        age = today.year - member.date_of_birth.year - (
            (today.month, today.day) < (member.date_of_birth.month, member.date_of_birth.day)
        )

        recommendations = []

        # 1. Age-based recommendations
        for min_age, max_age, title, desc, interval, priority, category in AGE_BASED_RULES:
            if age < min_age:
                continue
            if max_age is not None and age > max_age:
                continue
            recommendations.append({
                "title": title,
                "description": desc,
                "priority": priority,
                "category": category,
                "due_interval_months": interval,
                "source": "age-based",
            })

        # 2. Condition-based recommendations
        conditions_lower = (member.medical_history_summary or "").lower()
        for keyword, title, desc, interval, priority, category in CONDITION_RULES:
            if keyword in conditions_lower:
                if not any(r["title"] == title for r in recommendations):
                    recommendations.append({
                        "title": title,
                        "description": desc,
                        "priority": priority,
                        "category": category,
                        "due_interval_months": interval,
                        "source": "condition-based",
                    })

        # 3. Recent overdue follow-ups (within MAX_OVERDUE_DAYS only)
        overdue = await self._get_overdue_followups(member.id, today)
        for item in overdue:
            recommendations.append({
                "title": f"Follow-up: {item['title']}",
                "description": f"Was due {item['days_overdue']}d ago ({item['date']})",
                "priority": "high" if item["days_overdue"] <= 30 else "medium",
                "category": "follow-up",
                "due_interval_months": 0,
                "source": "overdue",
            })

        # Sort: high first, then medium, then low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda r: priority_order.get(str(r["priority"]), 3))

        return recommendations

    async def _get_overdue_followups(
        self, member_id: UUID, today: date
    ) -> list[dict]:
        """Find records with overdue next_review_date (within threshold)."""
        result = await self.db.execute(
            select(HealthRecord).where(
                HealthRecord.family_member_id == member_id,
                HealthRecord.is_deleted.is_(False),
                HealthRecord.next_review_date.isnot(None),
                HealthRecord.next_review_date < today,
                HealthRecord.next_review_date >= today - timedelta(days=MAX_OVERDUE_DAYS),
            )
        )
        records = result.scalars().all()

        overdue = []
        seen_dates: set[str] = set()
        for r in records:
            if not r.next_review_date:
                continue
            days_overdue = (today - r.next_review_date).days
            key = f"{r.next_review_date}-{r.record_type.value}"
            if key not in seen_dates:
                seen_dates.add(key)
                overdue.append({
                    "title": r.record_type.value.replace("_", " ").title(),
                    "date": str(r.next_review_date),
                    "days_overdue": days_overdue,
                })
        return overdue
