"""Notification service."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import Notification


class NotificationService:
    """Notification management service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def list_notifications(
        self,
        household_id: UUID,
        is_read: bool | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        """List notifications, unread first."""
        query = (
            select(Notification)
            .where(Notification.household_id == household_id)
            .order_by(Notification.is_read.asc(), Notification.created_at.desc())
            .limit(limit)
        )

        if is_read is not None:
            query = query.where(Notification.is_read == is_read)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def mark_as_read(self, notification_id: UUID, household_id: UUID) -> Notification:
        """Mark notification as read."""
        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.household_id == household_id,
            )
        )
        notification = result.scalar_one()
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await self.db.flush()
        return notification

    async def delete_notification(self, household_id: UUID, notification_id: UUID) -> None:
        """Delete a notification."""
        result = await self.db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.household_id == household_id,
            )
        )
        notification = result.scalar_one_or_none()
        if notification:
            await self.db.delete(notification)
            await self.db.flush()

    async def mark_all_as_read(self, household_id: UUID) -> int:
        """Mark all unread notifications as read. Returns count updated."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(Notification)
            .where(
                Notification.household_id == household_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=now)
        )
        await self.db.flush()
        return result.rowcount
