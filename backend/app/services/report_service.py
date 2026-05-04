"""Report service — generate PDF health reports."""
import json
import logging
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import HealthRecord, FamilyMember, Household
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)


def _parse_clinical(raw: str | None) -> dict | None:
    """Parse structured clinical_data JSON."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed.get("_type") == "structured":
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return None


class ReportService:
    """Generate PDF health reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_member_records(
        self, household_id: UUID, member_id: UUID | None = None
    ) -> list[tuple[FamilyMember, list[HealthRecord]]]:
        """Get records grouped by member."""
        query = (
            select(FamilyMember)
            .where(
                FamilyMember.household_id == str(household_id),
                FamilyMember.is_active.is_(True),
            )
            .order_by(FamilyMember.first_name)
        )
        if member_id:
            query = query.where(FamilyMember.id == str(member_id))

        result = await self.db.execute(query)
        members = list(result.scalars().all())

        grouped = []
        for member in members:
            rec_result = await self.db.execute(
                select(HealthRecord)
                .where(
                    HealthRecord.family_member_id == member.id,
                    HealthRecord.is_deleted.is_(False),
                )
                .order_by(HealthRecord.record_date.desc())
                .limit(50)
            )
            records = list(rec_result.scalars().all())
            grouped.append((member, records))

        return grouped

    async def _get_household_name(self, household_id: UUID) -> str:
        result = await self.db.execute(
            select(Household).where(Household.id == str(household_id))
        )
        hh = result.scalar_one_or_none()
        return hh.name if hh else "Family Health Manager"

    async def generate_health_summary_pdf(
        self,
        household_id: UUID,
        member_id: UUID | None = None,
    ) -> bytes:
        """Generate a health summary PDF."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDF not installed — cannot generate PDF")

        household_name = await self._get_household_name(household_id)
        member_data = await self._get_member_records(household_id, member_id)
        today = date.today().strftime("%B %d, %Y")

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # US Letter

        y = 50
        # Title
        page.insert_text((50, y), "Health Summary Report", fontsize=22, fontname="helv")
        y += 30
        page.insert_text((50, y), household_name, fontsize=14, fontname="helv")
        y += 18
        page.insert_text((50, y), f"Generated: {today}", fontsize=10, fontname="helv")
        y += 30

        # Horizontal rule
        page.draw_line((50, y), (562, y), color=(0.8, 0.8, 0.8))
        y += 20

        for member, records in member_data:
            if y > 700:
                page = doc.new_page(width=612, height=792)
                y = 50

            name = f"{member.first_name} {member.last_name}"
            page.insert_text((50, y), name, fontsize=16, fontname="helv")
            y += 20

            # Member details
            details = []
            if member.date_of_birth:
                details.append(f"DOB: {member.date_of_birth}")
            if member.gender:
                details.append(f"Gender: {member.gender}")
            if member.blood_group:
                details.append(f"Blood: {member.blood_group}")

            if details:
                page.insert_text((60, y), " | ".join(details), fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))
                y += 18

            page.insert_text((60, y), f"{len(records)} records", fontsize=9, fontname="helv", color=(0.5, 0.5, 0.5))
            y += 20

            # Recent records
            for record in records[:10]:
                if y > 720:
                    page = doc.new_page(width=612, height=792)
                    y = 50

                rec_date = str(record.record_date) if record.record_date else "No date"
                rec_type = record.record_type or "Unknown"
                diagnosis = record.diagnosis or ""

                line = f"  {rec_date}  |  {rec_type}"
                if diagnosis:
                    line += f"  |  {diagnosis[:60]}"

                page.insert_text((60, y), line, fontsize=9, fontname="helv")
                y += 14

                # Extract key data from structured records
                parsed = _parse_clinical(record.clinical_data)
                if parsed:
                    # Lab results
                    for key in ("lab_results", "lab_tests"):
                        tests = parsed.get(key, [])
                        if isinstance(tests, list):
                            for t in tests[:3]:
                                if isinstance(t, dict):
                                    test_line = f"    - {t.get('test_name', '?')}: {t.get('result', '?')} {t.get('units', '')} (ref: {t.get('ref_value', '-')})"
                                    if y > 720:
                                        page = doc.new_page(width=612, height=792)
                                        y = 50
                                    page.insert_text((60, y), test_line, fontsize=8, fontname="helv", color=(0.3, 0.3, 0.7))
                                    y += 12

                    # Prescriptions
                    for key in ("prescriptions", "medications"):
                        meds = parsed.get(key, [])
                        if isinstance(meds, list) and meds:
                            med_names = ", ".join(m.get("medicine", "?") for m in meds[:5] if isinstance(m, dict))
                            if y > 720:
                                page = doc.new_page(width=612, height=792)
                                y = 50
                            page.insert_text((60, y), f"    Rx: {med_names}", fontsize=8, fontname="helv", color=(0.2, 0.6, 0.2))
                            y += 12

                y += 6

            y += 15

        # Footer
        total_pages = len(doc)
        for i in range(total_pages):
            page = doc[i]
            page.insert_text(
                (50, 780),
                f"Page {i + 1} of {total_pages}  |  Health Keeper  |  Confidential",
                fontsize=7,
                fontname="helv",
                color=(0.6, 0.6, 0.6),
            )

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    async def generate_enhanced_health_pdf(
        self,
        household_id: UUID,
        member_id: UUID | None = None,
    ) -> bytes:
        """Generate an enhanced health summary PDF with risk summary, alerts, and preventive care."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDF not installed — cannot generate PDF")

        dashboard_svc = DashboardService(self.db)
        summary = await dashboard_svc.get_household_summary(household_id)
        household_name = await self._get_household_name(household_id)
        today = date.today().strftime("%B %d, %Y")

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        y = 50

        # Title
        page.insert_text((50, y), "Health Summary Report", fontsize=22, fontname="helv")
        y += 30
        page.insert_text((50, y), household_name, fontsize=14, fontname="helv")
        y += 18
        page.insert_text((50, y), f"Generated: {today}", fontsize=10, fontname="helv")
        y += 25

        # Risk Summary
        risk = summary.get("risk_summary", {})
        page.insert_text((50, y), "Risk Overview", fontsize=14, fontname="helv")
        y += 20
        risk_text = f"High risk: {risk.get('high_risk_members', 0)}  |  Moderate: {risk.get('moderate_risk_members', 0)}  |  Low: {risk.get('low_risk_members', 0)}"
        page.insert_text((60, y), risk_text, fontsize=10, fontname="helv")
        y += 20

        # Active Alerts
        alerts = summary.get("alerts", [])
        if alerts:
            page.insert_text((50, y), f"Active Alerts ({len(alerts)})", fontsize=14, fontname="helv")
            y += 20
            for alert in alerts[:8]:
                if y > 720:
                    page = doc.new_page(width=612, height=792)
                    y = 50
                sev = alert.get("severity", "info")
                title = alert.get("title", "")
                msg = alert.get("message", "")[:80]
                color = (0.8, 0.2, 0.2) if sev == "critical" else (0.7, 0.5, 0.1) if sev == "warning" else (0.3, 0.3, 0.7)
                page.insert_text((60, y), f"[{sev.upper()}] {title}", fontsize=9, fontname="helv", color=color)
                y += 14
                if msg:
                    page.insert_text((70, y), msg, fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
                    y += 14
            y += 10

        # Per-member scores with breakdown
        scores = summary.get("scores", [])
        if scores:
            if y > 600:
                page = doc.new_page(width=612, height=792)
                y = 50
            page.insert_text((50, y), "Member Health Scores", fontsize=14, fontname="helv")
            y += 22
            for s in scores:
                if y > 700:
                    page = doc.new_page(width=612, height=792)
                    y = 50
                name = f"{s['first_name']} {s['last_name']}"
                score = s.get("health_score", 0)
                risk_level = s.get("risk_level", "low")
                color = (0.2, 0.6, 0.2) if risk_level == "low" else (0.7, 0.5, 0.1) if risk_level == "moderate" else (0.8, 0.2, 0.2)
                page.insert_text((60, y), f"{name}: {score}/100 ({risk_level})", fontsize=10, fontname="helv", color=color)
                y += 16
                breakdown = s.get("score_breakdown", {})
                for key, val in breakdown.items():
                    label = val.get("label", key)[:60]
                    page.insert_text((80, y), f"{key.replace('_', ' ').title()}: {val['score']}/{val['max']} — {label}", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
                    y += 12
                y += 8

        # Preventive Care
        preventive = summary.get("preventive_care", [])
        if preventive:
            if y > 600:
                page = doc.new_page(width=612, height=792)
                y = 50
            page.insert_text((50, y), f"Preventive Care ({len(preventive)} items)", fontsize=14, fontname="helv")
            y += 22
            for item in preventive[:10]:
                if y > 720:
                    page = doc.new_page(width=612, height=792)
                    y = 50
                rec = item.get("recommendation", "")[:70]
                member_name = item.get("member_name", "")
                priority = item.get("priority", "")
                page.insert_text((60, y), f"{member_name}: {rec} [{priority}]", fontsize=9, fontname="helv")
                y += 14

        # Medication Summary
        med_summary = summary.get("medication_summary", {})
        if med_summary.get("total_active_medications", 0) > 0:
            if y > 650:
                page = doc.new_page(width=612, height=792)
                y = 50
            page.insert_text((50, y), "Medication Summary", fontsize=14, fontname="helv")
            y += 20
            page.insert_text((60, y), f"Active medications: {med_summary.get('total_active_medications', 0)} across {med_summary.get('members_with_medications', 0)} members", fontsize=10, fontname="helv")
            y += 16
            for refill in med_summary.get("refill_reminders", [])[:5]:
                med_name = refill.get("medicine", "")
                member_name = refill.get("member_name", "")
                page.insert_text((70, y), f"{member_name}: {med_name}", fontsize=9, fontname="helv", color=(0.5, 0.5, 0.5))
                y += 14

        # Footer
        total_pages = len(doc)
        for i in range(total_pages):
            page = doc[i]
            page.insert_text(
                (50, 780),
                f"Page {i + 1} of {total_pages}  |  Health Keeper  |  Confidential",
                fontsize=7,
                fontname="helv",
                color=(0.6, 0.6, 0.6),
            )

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
