"""Notification router."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_household_from_token
from app.services.notification_service import NotificationService
from app.schemas.notification import NotificationResponse
from app.models.base import Household

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
    is_read: bool | None = None,
    limit: int = Query(50, le=200),
):
    """List notifications (unread first)."""
    service = NotificationService(db)
    notifications = await service.list_notifications(household.id, is_read, limit)
    return notifications


@router.put("/read-all")
async def mark_all_read(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read."""
    service = NotificationService(db)
    count = await service.mark_all_as_read(household.id)
    return {"marked": count}


@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Mark notification as read."""
    service = NotificationService(db)

    try:
        notification = await service.mark_as_read(notification_id, household.id)
    except Exception:
        raise HTTPException(status_code=404, detail="Notification not found")

    return notification


@router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete notification."""
    service = NotificationService(db)

    try:
        await service.delete_notification(household.id, notification_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Notification not found")
