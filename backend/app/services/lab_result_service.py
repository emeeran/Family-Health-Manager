"""Lab result service — sync and query lab results from structured clinical_data."""
import json
import logging
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lab_result import LabResult

logger = logging.getLogger(__name__)


class LabResultService:
    """Manage lab results extracted from health record clinical_data."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_from_record(
        self,
        member_id: UUID,
        record_id: UUID,
        clinical_data_str: str,
        record_date: date,
    ) -> int:
        """Extract tests/lab_results from clinical_data and insert rows.

        Returns the number of lab result rows inserted.
        """
        parsed = self._parse_clinical_data(clinical_data_str)
        if not parsed or parsed.get("_type") != "structured":
            return 0

        tests = parsed.get("lab_results") or parsed.get("tests") or []
        if not isinstance(tests, list):
            return 0

        inserted = 0
        for t in tests:
            test_name = (t.get("test_name") or "").strip()
            result_val = (t.get("result") or "").strip()
            if not test_name or not result_val:
                continue

            self.db.add(LabResult(
                family_member_id=member_id,
                health_record_id=record_id,
                test_name=test_name,
                result=result_val,
                units=t.get("units", ""),
                ref_value=t.get("ref_value", ""),
                note=t.get("note", ""),
                record_date=record_date,
            ))
            inserted += 1

        if inserted:
            await self.db.flush()
        return inserted

    async def get_results_for_member(
        self,
        member_id: UUID,
        test_name: str | None = None,
    ) -> list[LabResult]:
        """Query lab results for a member, optionally filtered by test name."""
        query = (
            select(LabResult)
            .where(LabResult.family_member_id == member_id)
            .order_by(LabResult.record_date.desc())
        )
        if test_name:
            query = query.where(LabResult.test_name.ilike(f"%{test_name}%"))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_trends(
        self,
        member_id: UUID,
        test_names: list[str] | None = None,
    ) -> list[dict]:
        """Get date/result pairs for charting trends.

        Returns list of dicts: {test_name, record_date, result, units, ref_value}
        """
        query = (
            select(LabResult)
            .where(LabResult.family_member_id == member_id)
            .order_by(LabResult.test_name, LabResult.record_date)
        )
        if test_names:
            query = query.where(LabResult.test_name.in_(test_names))
        result = await self.db.execute(query)
        return [
            {
                "test_name": lr.test_name,
                "record_date": lr.record_date.isoformat() if lr.record_date else None,
                "result": lr.result,
                "units": lr.units,
                "ref_value": lr.ref_value,
            }
            for lr in result.scalars().all()
        ]

    @staticmethod
    def _parse_clinical_data(clinical_data: str | None) -> dict | None:
        """Safely parse clinical_data JSON string."""
        if not clinical_data:
            return None
        try:
            parsed = json.loads(clinical_data)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return None
