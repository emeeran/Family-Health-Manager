"""Unit tests for notification service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.services.notification_service import NotificationService
from app.models.base import Notification


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def notification_service(mock_db):
    """Create NotificationService instance."""
    return NotificationService(mock_db)


@pytest.mark.asyncio
async def test_list_notifications(notification_service, mock_db):
    """Test listing notifications."""
    household_id = uuid4()
    mock_notification = Notification(
        id=uuid4(),
        household_id=household_id,
        title="Test",
        is_read=False,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_notification]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await notification_service.list_notifications(household_id)

    assert len(result) == 1
    assert not result[0].is_read


@pytest.mark.asyncio
async def test_list_notifications_unread_first(notification_service, mock_db):
    """Test notifications are ordered unread first."""
    household_id = uuid4()
    read_notification = Notification(
        id=uuid4(),
        household_id=household_id,
        title="Read",
        is_read=True,
    )
    unread_notification = Notification(
        id=uuid4(),
        household_id=household_id,
        title="Unread",
        is_read=False,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [unread_notification, read_notification]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await notification_service.list_notifications(household_id)

    # Unread should come first
    assert not result[0].is_read
    assert result[1].is_read


@pytest.mark.asyncio
async def test_mark_as_read(notification_service, mock_db):
    """Test marking notification as read."""
    notification_id = uuid4()
    mock_notification = Notification(
        id=notification_id,
        household_id=uuid4(),
        title="Test",
        is_read=False,
    )

    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_notification
    mock_db.execute = AsyncMock(return_value=mock_result)

    household_id = uuid4()
    result = await notification_service.mark_as_read(notification_id, household_id)

    assert result.is_read
    assert result.read_at is not None


@pytest.mark.asyncio
async def test_delete_notification(notification_service, mock_db):
    """Test deleting a notification."""
    household_id = uuid4()
    notification_id = uuid4()
    mock_notification = Notification(
        id=notification_id,
        household_id=household_id,
        title="Test",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_notification
    mock_db.execute = AsyncMock(return_value=mock_result)

    await notification_service.delete_notification(household_id, notification_id)

    mock_db.delete.assert_called_once_with(mock_notification)


@pytest.mark.asyncio
async def test_delete_notification_not_found(notification_service, mock_db):
    """Test deleting non-existent notification."""
    household_id = uuid4()
    notification_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Should not raise, just silently ignore
    await notification_service.delete_notification(household_id, notification_id)
