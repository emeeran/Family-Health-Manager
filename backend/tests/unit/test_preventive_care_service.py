"""Unit tests for preventive care service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, timedelta
from uuid import uuid4

from app.services.preventive_care_service import PreventiveCareService
from app.models.base import FamilyMember, Gender, Relationship


@pytest.fixture
def mock_db():
    db = AsyncMock()
    # Default: no overdue follow-ups
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    # db.execute returns a coroutine that resolves to result_mock
    async def mock_execute(*args, **kwargs):
        return result_mock

    db.execute = mock_execute
    return db


@pytest.fixture
def service(mock_db):
    return PreventiveCareService(mock_db)


def _make_member(age: int, history: str = "") -> FamilyMember:
    """Create a FamilyMember instance with calculated DOB for given age."""
    today = date.today()
    dob = date(today.year - age, today.month, today.day)
    member = FamilyMember(
        id=uuid4(),
        household_id=uuid4(),
        first_name="Test",
        last_name="Patient",
        date_of_birth=dob,
        gender=Gender.MALE,
        relationship_type=Relationship.SELF,
        medical_history_summary=history,
    )
    return member


@pytest.mark.asyncio
async def test_get_overdue_followups_batch_groups_by_member(service, mock_db):
    """The batched query groups overdue follow-ups per member in one DB call."""
    m1, m2 = uuid4(), uuid4()
    rec1 = MagicMock()
    rec1.family_member_id = m1
    rec1.next_review_date = date.today() - timedelta(days=10)
    rec1.record_type.value = "doctor_visit"
    rec2 = MagicMock()
    rec2.family_member_id = m2
    rec2.next_review_date = date.today() - timedelta(days=40)
    rec2.record_type.value = "lab_report"

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [rec1, rec2]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    async def mock_execute(*args, **kwargs):
        return result_mock

    mock_db.execute = mock_execute

    grouped = await service.get_overdue_followups_batch([m1, m2], date.today())
    assert len(grouped[str(m1)]) == 1
    assert grouped[str(m1)][0]["days_overdue"] == 10
    assert len(grouped[str(m2)]) == 1
    assert grouped[str(m2)][0]["title"] == "Lab Report"


@pytest.mark.asyncio
async def test_generate_recommendations_uses_injected_overdue(service, mock_db):
    """When overdue_followups is supplied the service makes no DB query."""
    member = _make_member(40)
    injected = [{"title": "Thing", "date": "2026-01-01", "days_overdue": 5}]

    calls = {"n": 0}

    async def mock_execute(*args, **kwargs):
        calls["n"] += 1
        return MagicMock()

    mock_db.execute = mock_execute

    recs = await service.generate_recommendations(member, overdue_followups=injected)
    # generate_recommendations prefixes overdue titles with "Follow-up: ".
    assert "Follow-up: Thing" in [r["title"] for r in recs]
    assert calls["n"] == 0  # injected path → no DB round-trip


@pytest.mark.asyncio
async def test_age_based_rules_filter_by_age(service):
    """A 25-year-old should get rules with min_age<=25 and no upper bound >25."""
    member = _make_member(25)
    recs = await service.generate_recommendations(member)
    titles = [r["title"] for r in recs]

    # Should include: annual physical (18+), dental (18+), BP (18+)
    assert "Annual Physical Exam" in titles
    assert "Dental Check-up" in titles
    assert "Blood Pressure Screening" in titles

    # Should NOT include: lipid profile (30+), colorectal (50-75)
    assert "Annual Lipid Profile" not in titles
    assert "Colorectal Cancer Screening" not in titles


@pytest.mark.asyncio
async def test_age_based_rules_senior(service):
    """A 70-year-old should get senior-specific recommendations."""
    member = _make_member(70)
    recs = await service.generate_recommendations(member)
    titles = [r["title"] for r in recs]

    assert "Pneumococcal Vaccine" in titles
    assert "Shingles Vaccine (Shingrix)" in titles
    assert "Bone Density (DEXA)" in titles
    assert "Colorectal Cancer Screening" in titles  # 50-75 bracket


@pytest.mark.asyncio
async def test_condition_rules_diabetes(service):
    """Member with diabetes should get diabetes-specific recommendations."""
    member = _make_member(40, history="Conditions: Type 2 Diabetes, Hypertension")
    recs = await service.generate_recommendations(member)
    titles = [r["title"] for r in recs]

    assert "HbA1c Test (q3 months)" in titles
    assert "Diabetic Eye Exam" in titles
    assert "Diabetic Foot Exam" in titles
    assert "Kidney Function (uACR + eGFR)" in titles

    # Hypertension condition rules
    assert "Kidney Function Test" in titles
    assert "Quarterly BP Check" in titles


@pytest.mark.asyncio
async def test_condition_rules_no_match(service):
    """Member without matching conditions should not get condition-based recs."""
    member = _make_member(40, history="Conditions: None known")
    recs = await service.generate_recommendations(member)
    condition_recs = [r for r in recs if r["source"] == "condition-based"]
    assert len(condition_recs) == 0


@pytest.mark.asyncio
async def test_priority_sorting(service):
    """Recommendations should be sorted high -> medium -> low."""
    member = _make_member(65, history="Conditions: Diabetes")
    recs = await service.generate_recommendations(member)

    priorities = [r["priority"] for r in recs]
    priority_order = {"high": 0, "medium": 1, "low": 2}
    indices = [priority_order[p] for p in priorities]
    assert indices == sorted(indices)


@pytest.mark.asyncio
async def test_no_duplicate_condition_rules(service):
    """Condition rules should not duplicate titles."""
    member = _make_member(40, history="Conditions: Diabetes, Diabetes Mellitus")
    recs = await service.generate_recommendations(member)
    titles = [r["title"] for r in recs]
    # Even though 'diabetes' matches twice, titles should be unique
    assert titles.count("HbA1c Test (q3 months)") == 1


@pytest.mark.asyncio
async def test_source_field_populated(service):
    """Each recommendation should have a source field."""
    member = _make_member(30, history="Conditions: Asthma")
    recs = await service.generate_recommendations(member)
    for r in recs:
        assert r["source"] in ("age-based", "condition-based", "overdue")


@pytest.mark.asyncio
async def test_rule_structure(service):
    """Each recommendation should have all required fields."""
    member = _make_member(50)
    recs = await service.generate_recommendations(member)
    for r in recs:
        assert "title" in r
        assert "description" in r
        assert "priority" in r
        assert "category" in r
        assert "due_interval_months" in r
        assert r["priority"] in ("high", "medium", "low")
        assert r["category"] in ("vaccination", "screening", "lab", "follow-up")
