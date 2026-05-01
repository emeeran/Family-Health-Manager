"""Unit tests for preventive care service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
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
