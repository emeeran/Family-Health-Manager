"""Unit tests for provider service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from app.services.provider_service import ProviderService
from app.models.base import Provider, ProviderAssignment


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def provider_service(mock_db):
    """Create ProviderService instance."""
    return ProviderService(mock_db)


@pytest.mark.asyncio
async def test_create_provider(provider_service, mock_db):
    """Test creating a provider."""
    household_id = uuid4()

    provider = await provider_service.create_provider(
        household_id=household_id,
        name="Dr. Smith",
        speciality="Endocrinologist",
        phone="555-1234",
    )

    assert provider.name == "Dr. Smith"
    assert provider.household_id == household_id


@pytest.mark.asyncio
async def test_get_provider(provider_service, mock_db):
    """Test getting a provider."""
    household_id = uuid4()
    provider_id = uuid4()
    mock_provider = Provider(
        id=provider_id,
        household_id=household_id,
        name="Dr. Smith",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_provider
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await provider_service.get_provider(household_id, provider_id)

    assert result is not None
    assert result.id == provider_id


@pytest.mark.asyncio
async def test_get_provider_not_found(provider_service, mock_db):
    """Test getting non-existent provider."""
    household_id = uuid4()
    provider_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="Provider not found"):
        await provider_service.get_provider(household_id, provider_id)


@pytest.mark.asyncio
async def test_list_providers(provider_service, mock_db):
    """Test listing providers."""
    household_id = uuid4()
    mock_provider = Provider(
        id=uuid4(),
        household_id=household_id,
        name="Dr. Smith",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_provider]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await provider_service.list_providers(household_id)

    assert len(result) == 1
    assert result[0].name == "Dr. Smith"


@pytest.mark.asyncio
async def test_update_provider(provider_service, mock_db):
    """Test updating a provider."""
    provider_id = uuid4()
    mock_provider = Provider(
        id=provider_id,
        household_id=uuid4(),
        name="Dr. Smith",
        speciality="General",
    )

    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_provider
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await provider_service.update_provider(provider_id, speciality="Endocrinologist")

    assert result.speciality == "Endocrinologist"


@pytest.mark.asyncio
async def test_assign_provider_to_member(provider_service, mock_db):
    """Test assigning provider to member."""
    provider_id = uuid4()
    member_id = uuid4()

    assignment = await provider_service.assign_provider_to_member(
        provider_id=provider_id,
        member_id=member_id,
        uhid="UHID-123",
    )

    assert assignment.provider_id == provider_id
    assert assignment.family_member_id == member_id
    assert assignment.uhid == "UHID-123"


@pytest.mark.asyncio
async def test_get_member_providers(provider_service, mock_db):
    """Test getting providers for a member."""
    member_id = uuid4()
    mock_assignment = ProviderAssignment(
        id=uuid4(),
        provider_id=uuid4(),
        family_member_id=member_id,
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_assignment]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await provider_service.get_member_providers(member_id)

    assert len(result) == 1  # Returns list of (ProviderAssignment, Provider, FamilyMember) tuples


@pytest.mark.asyncio
async def test_remove_provider_assignment(provider_service, mock_db):
    """Test removing provider assignment."""
    assignment_id = uuid4()
    mock_assignment = ProviderAssignment(id=assignment_id)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_assignment
    mock_db.execute = AsyncMock(return_value=mock_result)

    household_id = uuid4()
    await provider_service.remove_provider_assignment(assignment_id, household_id)

    mock_db.delete.assert_called_once_with(mock_assignment)
