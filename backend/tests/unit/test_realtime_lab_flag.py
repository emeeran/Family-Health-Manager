"""Real-time abnormal-lab flagging at record save.

Creating/updating a LAB_REPORT record with an out-of-range value must produce a
HealthAlert immediately (previously only the 6h batch sweep caught these).
"""

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.base import (
    FamilyMember,
    Gender,
    HealthAlert,
    Household,
    RecordType,
    Relationship,
    User,
)
from app.services.health_record_service import HealthRecordService

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def member(db_session):
    user = User(id=uuid4(), username="labflag", password_hash="x")
    household = Household(id=uuid4(), name="H", primary_user_id=user.id)
    m = FamilyMember(
        id=uuid4(),
        household_id=household.id,
        first_name="Lab",
        last_name="Patient",
        date_of_birth=date(1980, 1, 1),
        gender=Gender.MALE,
        relationship_type=Relationship.SELF,
    )
    db_session.add_all([user, household, m])
    await db_session.commit()
    return m


def _lab_data(result: str, ref: str) -> str:
    import json

    return json.dumps(
        {
            "_type": "structured",
            "lab_results": [
                {"test_name": "Glucose", "result": result, "ref_value": ref}
            ],
        }
    )


async def test_out_of_range_high_creates_alert_immediately(db_session, member):
    """A glucose far above range flags a CRITICAL alert on record create."""
    record = await HealthRecordService(db_session).create_record(
        member_id=member.id,
        record_type=RecordType.LAB_REPORT,
        record_date=date(2026, 1, 1),
        clinical_data=_lab_data("300 mg/dL", "70-100 mg/dL"),
    )
    await db_session.commit()
    alerts = (
        await db_session.execute(select(HealthAlert).where(HealthAlert.record_id == str(record.id)))
    ).scalars().all()
    assert len(alerts) == 1
    assert "Glucose" in alerts[0].title
    assert "HIGH" in alerts[0].title


async def test_in_range_value_creates_no_alert(db_session, member):
    await HealthRecordService(db_session).create_record(
        member_id=member.id,
        record_type=RecordType.LAB_REPORT,
        record_date=date(2026, 1, 2),
        clinical_data=_lab_data("85 mg/dL", "70-100 mg/dL"),
    )
    await db_session.commit()
    alerts = (
        await db_session.execute(select(HealthAlert).where(HealthAlert.family_member_id == str(member.id)))
    ).scalars().all()
    assert alerts == []


async def test_non_lab_record_creates_no_alert(db_session, member):
    """A prescription record is never scanned for lab anomalies."""
    await HealthRecordService(db_session).create_record(
        member_id=member.id,
        record_type=RecordType.DOCTOR_VISIT,
        record_date=date(2026, 1, 3),
        clinical_data='{"diagnosis": "hypertension"}',
    )
    await db_session.commit()
    alerts = (
        await db_session.execute(select(HealthAlert).where(HealthAlert.family_member_id == str(member.id)))
    ).scalars().all()
    assert alerts == []


async def test_update_with_new_out_of_range_flags(db_session, member):
    """Editing clinical_data to an out-of-range value flags on update."""
    svc = HealthRecordService(db_session)
    record = await svc.create_record(
        member_id=member.id,
        record_type=RecordType.LAB_REPORT,
        record_date=date(2026, 1, 4),
        clinical_data=_lab_data("85 mg/dL", "70-100 mg/dL"),
    )
    await db_session.commit()
    await svc.update_record(record.id, clinical_data=_lab_data("400 mg/dL", "70-100 mg/dL"))
    await db_session.commit()
    alerts = (
        await db_session.execute(select(HealthAlert).where(HealthAlert.record_id == str(record.id)))
    ).scalars().all()
    assert len(alerts) == 1
