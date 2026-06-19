"""Lab result service — sync and query lab results from structured clinical_data."""

import logging
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.parsing import parse_clinical_data
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
        parsed = parse_clinical_data(clinical_data_str)
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

            self.db.add(
                LabResult(
                    family_member_id=member_id,
                    health_record_id=record_id,
                    test_name=test_name,
                    result=result_val,
                    units=t.get("units", ""),
                    ref_value=t.get("ref_value", ""),
                    note=t.get("note", ""),
                    record_date=record_date,
                )
            )
            inserted += 1

        if inserted:
            await self.db.flush()
        return inserted
