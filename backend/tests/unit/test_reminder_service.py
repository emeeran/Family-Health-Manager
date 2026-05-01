"""Unit tests for reminder service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from uuid import uuid4
from app.services.reminder_service import ReminderService
from app.models.base import Reminder, ReminderType, ScheduleType


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def reminder_service(mock_db):
    """Create ReminderService instance."""
    return ReminderService(mock_db)


@pytest.mark.asyncio
async def test_create_reminder(reminder_service, mock_db):
    """Test creating a reminder."""
    household_id = uuid4()

    reminder = await reminder_service.create_reminder(
        household_id=household_id,
        reminder_type=ReminderType.MEDICATION,
        title="Take Medicine",
        start_datetime=datetime(2024, 1, 15, 8, 0),
        schedule_type=ScheduleType.DAILY,
    )

    assert reminder.reminder_type == ReminderType.MEDICATION
    assert reminder.household_id == household_id


@pytest.mark.asyncio
async def test_get_reminder(reminder_service, mock_db):
    """Test getting a reminder."""
    household_id = uuid4()
    reminder_id = uuid4()
    mock_reminder = Reminder(
        id=reminder_id,
        household_id=household_id,
        reminder_type=ReminderType.MEDICATION,
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_reminder
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await reminder_service.get_reminder(household_id, reminder_id)

    assert result is not None
    assert result.id == reminder_id


@pytest.mark.asyncio
async def test_get_reminder_not_found(reminder_service, mock_db):
    """Test getting non-existent reminder."""
    household_id = uuid4()
    reminder_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="Reminder not found"):
        await reminder_service.get_reminder(household_id, reminder_id)


@pytest.mark.asyncio
async def test_list_reminders(reminder_service, mock_db):
    """Test listing reminders."""
    household_id = uuid4()
    mock_reminder = Reminder(
        id=uuid4(),
        household_id=household_id,
        reminder_type=ReminderType.MEDICATION,
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_reminder]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await reminder_service.list_reminders(household_id)

    assert len(result) == 1
    assert result[0].reminder_type == ReminderType.MEDICATION


@pytest.mark.asyncio
async def test_update_reminder(reminder_service, mock_db):
    """Test updating a reminder."""
    household_id = uuid4()
    reminder_id = uuid4()
    mock_reminder = Reminder(
        id=reminder_id,
        household_id=household_id,
        title="Old Title",
        is_active=True,
    )

    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_reminder
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await reminder_service.update_reminder(reminder_id, household_id, title="New Title")

    assert result.title == "New Title"


@pytest.mark.asyncio
async def test_process_due_reminders(reminder_service, mock_db):
    """Test processing due reminders."""
    mock_reminder = Reminder(
        id=uuid4(),
        household_id=uuid4(),
        title="Test Reminder",
        is_active=True,
        start_datetime=datetime(2024, 1, 1),
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_reminder]
    mock_db.execute = AsyncMock(return_value=mock_result)

    notifications = await reminder_service.process_due_reminders()

    assert len(notifications) == 1
    assert notifications[0].title == "Test Reminder"
