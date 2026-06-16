"""Unit tests for member service."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from uuid import uuid4
from app.services.member_service import MemberService
from app.models.base import FamilyMember, Gender, Relationship, HealthRecord, RecordType
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


# ── Vitals sync (doctor visit → member profile + VITALS record) ──


def test_build_vitals_payload_bmi_and_keys():
    """Payload carries bmi/height_cm/weight_kg (+ bp/hr/temp) and the source tag."""
    visit_id = uuid4()
    payload = MemberService._build_vitals_payload(
        height_cm=175.0,
        weight_kg=80.0,
        blood_pressure="120/80",
        heart_rate="72",
        temperature="98.6",
        source_visit_id=visit_id,
    )
    assert payload is not None
    assert payload["_type"] == "structured"
    assert payload["bmi"] == 26.1  # 80 / 1.75^2
    assert payload["height_cm"] == 175.0
    assert payload["weight_kg"] == 80.0
    assert payload["blood_pressure"] == "120/80"
    assert payload["_source_visit"] == str(visit_id)


def test_build_vitals_payload_none_when_empty():
    """No vital values → None (caller should skip)."""
    assert MemberService._build_vitals_payload() is None
    # A source tag alone is not a vital.
    assert MemberService._build_vitals_payload(source_visit_id=uuid4()) is None


@pytest.mark.asyncio
async def test_sync_vitals_from_visit_creates_record(member_service, mock_db):
    """First sync updates the member profile and creates a tagged VITALS record."""
    member_id = uuid4()
    visit_id = uuid4()
    mock_member = FamilyMember(
        id=member_id, household_id=uuid4(), first_name="John", last_name="Doe"
    )
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = mock_member
    vitals_result = MagicMock()
    vitals_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(side_effect=[member_result, vitals_result])

    await member_service.sync_vitals_from_visit(
        member_id,
        date(2026, 6, 16),
        {"weight": "80", "height": "175", "blood_pressure": "120/80"},
        visit_id,
    )

    assert mock_member.weight_kg == 80.0
    assert mock_member.height_cm == 175.0
    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert added.record_type == RecordType.VITALS
    assert added.record_date == date(2026, 6, 16)
    data = json.loads(added.clinical_data)
    assert data["bmi"] == 26.1
    assert data["height_cm"] == 175.0
    assert data["weight_kg"] == 80.0
    assert data["blood_pressure"] == "120/80"
    assert data["_source_visit"] == str(visit_id)


@pytest.mark.asyncio
async def test_sync_vitals_updates_existing_tagged_record(member_service, mock_db):
    """Editing a visit updates the same VITALS row in place (no duplicate)."""
    member_id = uuid4()
    visit_id = uuid4()
    mock_member = FamilyMember(
        id=member_id, household_id=uuid4(), first_name="John", last_name="Doe"
    )
    existing = HealthRecord(
        id=uuid4(),
        family_member_id=member_id,
        record_type=RecordType.VITALS,
        record_date=date(2026, 6, 1),
        clinical_data=json.dumps(
            {"_type": "structured", "_source_visit": str(visit_id), "bmi": 25.0}
        ),
    )
    member_result = MagicMock()
    member_result.scalar_one_or_none.return_value = mock_member
    vitals_result = MagicMock()
    vitals_result.scalars.return_value.all.return_value = [existing]
    mock_db.execute = AsyncMock(side_effect=[member_result, vitals_result])

    await member_service.sync_vitals_from_visit(
        member_id, date(2026, 6, 16), {"weight": "90"}, visit_id
    )

    mock_db.add.assert_not_called()  # updated in place, not re-created
    data = json.loads(existing.clinical_data)
    assert data["weight_kg"] == 90.0
    assert existing.record_date == date(2026, 6, 16)


@pytest.mark.asyncio
async def test_sync_vitals_noop_when_empty(member_service, mock_db):
    """No vital values present → nothing happens."""
    await member_service.sync_vitals_from_visit(
        uuid4(), date(2026, 6, 16), {"weight": "", "height": None}, uuid4()
    )
    mock_db.add.assert_not_called()
    mock_db.execute.assert_not_called()
