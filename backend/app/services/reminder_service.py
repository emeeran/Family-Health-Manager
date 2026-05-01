"""Reminder service."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import update_model
from app.models.base import Reminder, Notification, ReminderType, ScheduleType


class ReminderService:
    """Reminder management service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def create_follow_up_if_not_exists(
        self,
        household_id: UUID,
        member_id: UUID,
        review_date: datetime,
        title: str,
        description: str | None = None,
    ) -> Reminder | None:
        """Create a FOLLOW_UP reminder only if one doesn't already exist
        for this member on the same review date."""
        # Check for existing FOLLOW_UP reminder for same member on same date
        day_start = datetime.combine(review_date.date(), datetime.min.time())
        day_end = datetime.combine(review_date.date(), datetime.max.time())

        result = await self.db.execute(
            select(Reminder).where(
                Reminder.household_id == household_id,
                Reminder.family_member_id == member_id,
                Reminder.reminder_type == ReminderType.FOLLOW_UP,
                Reminder.start_datetime >= day_start,
                Reminder.start_datetime <= day_end,
                Reminder.is_active,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return None  # Already exists, skip

        return await self.create_reminder(
            household_id=household_id,
            reminder_type=ReminderType.FOLLOW_UP,
            title=title,
            description=description,
            schedule_type=ScheduleType.ONCE,
            start_datetime=review_date,
            member_id=member_id,
        )

    async def create_reminder(
        self,
        household_id: UUID,
        reminder_type: ReminderType,
        title: str,
        start_datetime: datetime,
        schedule_type: ScheduleType,
        description: str | None = None,
        schedule_interval: int | None = None,
        end_datetime: datetime | None = None,
        member_id: UUID | None = None,
    ) -> Reminder:
        """Create a new reminder."""
        reminder = Reminder(
            household_id=household_id,
            reminder_type=reminder_type,
            title=title,
            description=description,
            schedule_type=schedule_type,
            schedule_interval=schedule_interval,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            family_member_id=member_id,
        )
        self.db.add(reminder)
        await self.db.flush()
        return reminder

    async def get_reminder(self, household_id: UUID, reminder_id: UUID) -> Reminder:
        """Get reminder by ID, ensuring household access."""
        result = await self.db.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.household_id == household_id,
            )
        )
        reminder = result.scalar_one_or_none()
        if not reminder:
            raise ValueError("Reminder not found")
        return reminder

    async def list_reminders(
        self,
        household_id: UUID,
        reminder_type: ReminderType | None = None,
        is_active: bool | None = None,
        member_id: UUID | None = None,
    ) -> list[Reminder]:
        """List reminders with optional filters."""
        query = select(Reminder).where(Reminder.household_id == household_id)

        if reminder_type:
            query = query.where(Reminder.reminder_type == reminder_type)
        if is_active is not None:
            query = query.where(Reminder.is_active == is_active)
        if member_id:
            query = query.where(Reminder.family_member_id == member_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_reminder(self, reminder_id: UUID, household_id: UUID, **kwargs) -> Reminder:
        """Update reminder details."""
        allowed = {
            "title", "description", "reminder_type", "schedule_type",
            "schedule_interval", "start_datetime", "end_datetime", "is_active",
        }
        result = await self.db.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.household_id == household_id,
            )
        )
        reminder = result.scalar_one()
        return await update_model(self.db, reminder, allowed_fields=allowed, **kwargs)

    async def delete_reminder(self, household_id: UUID, reminder_id: UUID) -> None:
        """Delete a reminder."""
        reminder = await self.get_reminder(household_id, reminder_id)
        await self.db.delete(reminder)
        await self.db.flush()

    async def process_due_reminders(self) -> list[Notification]:
        """Process due reminders and create notifications."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(Reminder).where(
                Reminder.is_active,
                Reminder.start_datetime <= now,
            )
        )
        reminders = result.scalars().all()

        if not reminders:
            return []

        # Batch insert all notifications in one query
        values = [
            {
                "reminder_id": r.id,
                "household_id": r.household_id,
                "title": r.title,
                "message": r.description or r.title,
            }
            for r in reminders
        ]
        await self.db.execute(insert(Notification).values(values))
        await self.db.flush()

        # Deactivate processed reminders / advance recurring schedules
        for r in reminders:
            if r.schedule_type == ScheduleType.ONCE:
                r.is_active = False
            elif r.schedule_type == ScheduleType.CUSTOM and r.schedule_interval:
                r.start_datetime = r.start_datetime + timedelta(minutes=r.schedule_interval)

        await self.db.flush()

        # Return lightweight Notification-like objects for the caller
        notifications = [
            Notification(
                reminder_id=r.id,
                household_id=r.household_id,
                title=r.title,
                message=r.description or r.title,
            )
            for r in reminders
        ]
        return notifications
