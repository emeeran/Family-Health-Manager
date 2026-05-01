"""Unit tests for insight service."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.insight_service import InsightService
from app.models.base import HealthRecord, RecordType


class TestBuildPrompt:
    """Test _build_prompt for different record types."""

    @pytest.fixture
    def service(self):
        return InsightService(AsyncMock())

    def _make_record(self, record_type: RecordType, clinical_data: str = "", diagnosis: str = "") -> HealthRecord:
        record = MagicMock(spec=HealthRecord)
        record.record_type = record_type
        record.clinical_data = clinical_data
        record.diagnosis = diagnosis
        record.record_date = "2026-04-30"
        return record

    def test_lab_report_prompt(self, service):
        record = self._make_record(RecordType.LAB_REPORT, '{"glucose": 120}')
        prompt = service._build_prompt(record)
        assert "reviewing physician" in prompt
        assert '{"glucose": 120}' in prompt

    def test_doctor_visit_prompt_with_medications(self, service):
        clinical_data = json.dumps({
            "_type": "structured",
            "prescriptions": [
                {"type": "Tab", "medicine": "Metformin", "dosage": "500mg"}
            ],
        })
        record = self._make_record(RecordType.DOCTOR_VISIT, clinical_data, "Type 2 Diabetes")
        prompt = service._build_prompt(record)
        assert "reviewing physician" in prompt
        assert "Metformin" in prompt
        assert "Type 2 Diabetes" in prompt

    def test_blood_glucose_prompt(self, service):
        record = self._make_record(RecordType.BLOOD_GLUCOSE, '{"glucose_value": 150}')
        prompt = service._build_prompt(record)
        assert "glucose" in prompt.lower()

    def test_default_prompt_for_unknown_type(self, service):
        record = self._make_record(RecordType.MISC_RECORD, "Some data")
        prompt = service._build_prompt(record)
        # Default prompt should be used
        assert len(prompt) > 0

    def test_empty_clinical_data(self, service):
        record = self._make_record(RecordType.LAB_REPORT, "")
        prompt = service._build_prompt(record)
        assert len(prompt) > 0  # Should not crash

    def test_invalid_json_clinical_data(self, service):
        record = self._make_record(RecordType.DOCTOR_VISIT, "not json {{{")
        prompt = service._build_prompt(record)
        assert "N/A" in prompt  # Medications should default to N/A


class TestSpawnTasks:
    """Test fire-and-forget task spawning."""

    def test_spawn_insight_task_no_event_loop(self):
        """Should not raise when no event loop is available."""
        from app.services.insight_service import spawn_insight_task

        with patch("app.services.insight_service.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("No loop")
            spawn_insight_task(uuid4())  # Should not raise

    def test_spawn_verification_task_no_event_loop(self):
        """Should not raise when no event loop is available."""
        from app.services.insight_service import spawn_insight_verification_task

        with patch("app.services.insight_service.asyncio") as mock_asyncio:
            mock_asyncio.get_running_loop.side_effect = RuntimeError("No loop")
            spawn_insight_verification_task(uuid4(), "context")  # Should not raise
