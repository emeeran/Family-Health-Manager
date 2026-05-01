"""Health alert service — CRUD for proactive health notifications."""
import logging
from datetime import date
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_alert import HealthAlert, AlertSeverity, AlertType

logger = logging.getLogger(__name__)


class HealthAlertService:
    """Manage proactive health alerts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_alert(
        self,
        household_id: UUID,
        member_id: UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        record_id: UUID | None = None,
        test_name: str | None = None,
        value: str | None = None,
        reference: str | None = None,
    ) -> HealthAlert:
        """Create a new health alert."""
        alert = HealthAlert(
            household_id=str(household_id),
            family_member_id=str(member_id),
            record_id=str(record_id) if record_id else None,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            test_name=test_name,
            value=value,
            reference=reference,
        )
        self.db.add(alert)
        await self.db.flush()
        return alert

    async def check_duplicate(
        self, member_id: UUID, test_name: str, record_date: date
    ) -> bool:
        """Check if an alert already exists for this member/test/date."""
        result = await self.db.execute(
            select(HealthAlert).where(
                and_(
                    HealthAlert.family_member_id == str(member_id),
                    HealthAlert.test_name == test_name,
                    HealthAlert.is_dismissed.is_(False),
                    func.date(HealthAlert.created_at) == record_date,
                )
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def batch_check_duplicates(
        self, member_id: UUID
    ) -> set[tuple[str, date]]:
        """Return set of (test_name, date) tuples for existing undismissed alerts.

        Used to batch-check duplicates and avoid N+1 queries in anomaly detection.
        """
        result = await self.db.execute(
            select(HealthAlert.test_name, func.date(HealthAlert.created_at)).where(
                HealthAlert.family_member_id == str(member_id),
                HealthAlert.is_dismissed.is_(False),
                HealthAlert.test_name.isnot(None),
            )
        )
        return {(row[0], row[1]) for row in result.all()}

    async def list_alerts(
        self,
        household_id: UUID,
        member_id: UUID | None = None,
        severity: AlertSeverity | None = None,
        dismissed: bool | None = False,
    ) -> list[HealthAlert]:
        """List alerts for a household with optional filters."""
        query = select(HealthAlert).where(
            HealthAlert.household_id == str(household_id),
        )
        if member_id:
            query = query.where(HealthAlert.family_member_id == str(member_id))
        if severity:
            query = query.where(HealthAlert.severity == severity)
        if dismissed is True:
            query = query.where(HealthAlert.is_dismissed.is_(True))
        elif dismissed is False:
            query = query.where(HealthAlert.is_dismissed.is_(False))
        query = query.order_by(HealthAlert.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def dismiss_alert(self, alert_id: UUID, household_id: UUID | None = None) -> HealthAlert:
        """Dismiss a health alert."""
        query = select(HealthAlert).where(HealthAlert.id == str(alert_id))
        if household_id:
            query = query.where(HealthAlert.household_id == str(household_id))
        result = await self.db.execute(query)
        alert = result.scalar_one_or_none()
        if not alert:
            raise ValueError("Alert not found")
        alert.is_dismissed = True
        await self.db.flush()
        return alert

    async def get_undismissed_count(self, household_id: UUID) -> int:
        """Get count of undismissed alerts for badge display."""
        result = await self.db.execute(
            select(func.count()).where(
                HealthAlert.household_id == str(household_id),
                HealthAlert.is_dismissed.is_(False),
            )
        )
        return result.scalar() or 0
