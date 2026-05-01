"""Unit tests for household service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.services.household_service import HouseholdService
from app.models.base import Household


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def household_service(mock_db):
    """Create HouseholdService instance."""
    return HouseholdService(mock_db)


@pytest.mark.asyncio
async def test_get_household_by_user(household_service, mock_db):
    """Test getting household by user ID."""
    user_id = uuid4()
    mock_household = Household(id=uuid4(), primary_user_id=user_id, name="Test Household")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_household
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await household_service.get_household_by_user(user_id)

    assert result is not None
    assert result.primary_user_id == user_id


@pytest.mark.asyncio
async def test_get_household_by_user_not_found(household_service, mock_db):
    """Test getting household for non-existent user."""
    user_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await household_service.get_household_by_user(user_id)

    assert result is None


@pytest.mark.asyncio
async def test_get_household(household_service, mock_db):
    """Test getting household by ID."""
    household_id = uuid4()
    mock_household = Household(id=household_id, primary_user_id=uuid4(), name="Test Household")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_household
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await household_service.get_household(household_id)

    assert result is not None
    assert result.id == household_id


@pytest.mark.asyncio
async def test_update_household(household_service, mock_db):
    """Test updating household name."""
    household_id = uuid4()
    new_name = "Updated Household"
    mock_household = Household(id=household_id, primary_user_id=uuid4(), name="Old Name")

    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_household
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await household_service.update_household(household_id, new_name)

    assert result.name == new_name
    mock_db.flush.assert_called_once()
