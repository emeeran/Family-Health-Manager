"""Unit tests for member service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from uuid import uuid4
from app.services.member_service import MemberService
from app.models.base import FamilyMember, Gender, Relationship
from app.schemas.family_member import MedicalHistoryQuestionnaire


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def member_service(mock_db):
    """Create MemberService instance."""
    return MemberService(mock_db)


@pytest.mark.asyncio
async def test_create_member(member_service, mock_db):
    """Test creating a family member."""
    household_id = uuid4()

    member = await member_service.create_member(
        household_id=household_id,
        first_name="John",
        last_name="Doe",
        date_of_birth=date(1990, 1, 1),
        gender=Gender.MALE,
        relationship=Relationship.SELF,
    )

    assert member.first_name == "John"
    assert member.household_id == household_id


@pytest.mark.asyncio
async def test_create_member_with_medical_history(member_service, mock_db):
    """Test creating member with medical history."""
    household_id = uuid4()
    medical_history = MedicalHistoryQuestionnaire(
        conditions="Diabetes",
        allergies="Penicillin",
        current_medications="Metformin",
        past_surgeries="Appendectomy",
    )

    member = await member_service.create_member(
        household_id=household_id,
        first_name="John",
        last_name="Doe",
        date_of_birth=date(1990, 1, 1),
        gender=Gender.MALE,
        relationship=Relationship.SELF,
        medical_history=medical_history,
    )

    assert "Conditions: Diabetes" in member.medical_history_summary
    assert "Allergies: Penicillin" in member.medical_history_summary


@pytest.mark.asyncio
async def test_get_member(member_service, mock_db):
    """Test getting member by ID."""
    household_id = uuid4()
    member_id = uuid4()
    mock_member = FamilyMember(
        id=member_id,
        household_id=household_id,
        first_name="John",
        last_name="Doe",
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_member
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await member_service.get_member(household_id, member_id)

    assert result is not None
    assert result.id == member_id


@pytest.mark.asyncio
async def test_get_member_not_found(member_service, mock_db):
    """Test getting non-existent member."""
    household_id = uuid4()
    member_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="Member not found"):
        await member_service.get_member(household_id, member_id)


@pytest.mark.asyncio
async def test_list_members(member_service, mock_db):
    """Test listing members."""
    household_id = uuid4()
    mock_member = FamilyMember(
        id=uuid4(),
        household_id=household_id,
        first_name="John",
        last_name="Doe",
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_member]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await member_service.list_members(household_id)

    assert len(result) == 1
    assert result[0].first_name == "John"


@pytest.mark.asyncio
async def test_soft_delete_member(member_service, mock_db):
    """Test soft-deleting a member."""
    household_id = uuid4()
    member_id = uuid4()
    mock_member = FamilyMember(
        id=member_id,
        household_id=household_id,
        first_name="John",
        last_name="Doe",
        is_active=True,
    )

    get_result = MagicMock()
    get_result.scalar_one_or_none.return_value = mock_member

    mock_db.execute = AsyncMock(return_value=get_result)

    await member_service.soft_delete_member(household_id, member_id)

    assert not mock_member.is_active
