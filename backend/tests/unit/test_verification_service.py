"""Unit tests for verification service."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.verification_service import VerificationService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_ai_service():
    ai = AsyncMock()
    return ai


@pytest.fixture
def service(mock_db, mock_ai_service):
    return VerificationService(mock_db, mock_ai_service)


class TestParseVerificationResponse:
    """Test the static _parse_verification_response method."""

    def test_valid_json(self):
        raw = '{"status": "verified", "claims_checked": 3, "warnings": [], "summary": "All good"}'
        result = VerificationService._parse_verification_response(raw)
        assert result is not None
        assert result["status"] == "verified"
        assert result["claims_checked"] == 3

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"status": "warnings", "claims_checked": 1, "warnings": [{"type": "wrong_date"}], "summary": "Date wrong"}\n```'
        result = VerificationService._parse_verification_response(raw)
        assert result is not None
        assert result["status"] == "warnings"

    def test_none_input(self):
        result = VerificationService._parse_verification_response(None)
        assert result is None

    def test_empty_input(self):
        result = VerificationService._parse_verification_response("")
        assert result is None

    def test_embedded_json(self):
        raw = 'Here is the result: {"status": "unverifiable", "claims_checked": 0, "warnings": [], "summary": "No data"} end'
        result = VerificationService._parse_verification_response(raw)
        assert result is not None
        assert result["status"] == "unverifiable"

    def test_invalid_json(self):
        raw = "not json at all"
        result = VerificationService._parse_verification_response(raw)
        assert result is None


class TestVerifyInsight:
    """Test verify_insight method."""

    @pytest.mark.asyncio
    async def test_verify_insight_success(self, service, mock_ai_service, mock_db):
        """Successful verification updates insight fields."""
        insight = MagicMock()
        insight.id = uuid4()
        insight.response = "Patient has diabetes"
        insight.provider_used = "Ollama medgemma"

        mock_ai_service._call_validator.return_value = (
            '{"status": "verified", "claims_checked": 2, "warnings": [], "summary": "Accurate"}',
            "Cloud AI",
        )

        await service.verify_insight(insight, "Patient context here")

        assert insight.verification_status == "verified"
        assert insight.verification_claims_checked == 2
        assert insight.verification_verifier == "Cloud AI"
        assert insight.verification_at is not None
        mock_db.flush.assert_called()

    @pytest.mark.asyncio
    async def test_verify_insight_with_warnings(self, service, mock_ai_service, mock_db):
        """Verification with warnings populates warnings_json."""
        insight = MagicMock()
        insight.id = uuid4()
        insight.response = "Patient HbA1c is 8.5%"
        insight.provider_used = "Ollama medgemma"

        warnings = [
            {
                "type": "wrong_value",
                "claim": "HbA1c 8.5%",
                "correction": "HbA1c is 7.2%",
                "severity": "high",
            }
        ]
        mock_ai_service._call_validator.return_value = (
            json.dumps(
                {
                    "status": "warnings",
                    "claims_checked": 1,
                    "warnings": warnings,
                    "summary": "Value mismatch",
                }
            ),
            "Cloud AI",
        )

        await service.verify_insight(insight, "Patient context")

        assert insight.verification_status == "warnings"
        assert insight.verification_warnings_json is not None

    @pytest.mark.asyncio
    async def test_verify_insight_ai_failure(self, service, mock_ai_service, mock_db):
        """AI service failure sets status to 'failed'."""
        insight = MagicMock()
        insight.id = uuid4()
        insight.response = "Some text"
        insight.provider_used = "Ollama medgemma"

        mock_ai_service._call_validator.side_effect = RuntimeError("AI unavailable")

        await service.verify_insight(insight, "context")

        assert insight.verification_status == "failed"
        assert insight.verification_at is not None

    @pytest.mark.asyncio
    async def test_verify_insight_no_validator(self, service, mock_ai_service):
        """No different-family validator available -> 'unvalidated' (content still shown)."""
        insight = MagicMock()
        insight.id = uuid4()
        insight.response = "Some text"
        insight.provider_used = "Ollama medgemma"

        mock_ai_service._call_validator.return_value = None

        await service.verify_insight(insight, "context")

        assert insight.verification_status == "unvalidated"
        assert insight.verification_verifier is None
        assert insight.verification_at is not None


class TestVerifyExtraction:
    """Test verify_extraction method."""

    @pytest.mark.asyncio
    async def test_verify_extraction_success(self, service, mock_ai_service):
        mock_ai_service._call_validator.return_value = (
            '{"status": "verified", "claims_checked": 3, "warnings": [], "summary": "Extraction looks good"}',
            "Cloud AI",
        )

        result = await service.verify_extraction(
            {"medicine": "Metformin", "dosage": "500mg"},
            "Ollama medgemma",
        )

        assert result["status"] == "verified"
        assert result["verifier_provider"] == "Cloud AI"
        assert "verified_at" in result

    @pytest.mark.asyncio
    async def test_verify_extraction_failure(self, service, mock_ai_service):
        mock_ai_service._call_validator.side_effect = Exception("Service down")

        result = await service.verify_extraction({}, "Ollama medgemma")

        assert result["status"] == "failed"
        assert result["claims_checked"] == 0

    @pytest.mark.asyncio
    async def test_verify_extraction_no_validator(self, service, mock_ai_service):
        """No different-family validator available -> 'unvalidated'."""
        mock_ai_service._call_validator.return_value = None

        result = await service.verify_extraction({"medicine": "Metformin"}, "Ollama medgemma")

        assert result["status"] == "unvalidated"
        assert result["verifier_provider"] == ""


class TestVerifyDrugInfo:
    """Test verify_drug_info (flyout content cross-check)."""

    @pytest.mark.asyncio
    async def test_verify_drug_info_success(self, service, mock_ai_service):
        mock_ai_service._call_validator.return_value = (
            '{"status": "verified", "claims_checked": 3, "warnings": [], '
            '"summary": "Content matches Metformin"}',
            "Cloud AI",
        )
        result = await service.verify_drug_info(
            "Metformin", {"indication": "type 2 diabetes", "adverse_events": ["nausea"]}
        )
        assert result["status"] == "verified"
        assert result["verifier_provider"] == "Cloud AI"
        assert "verified_at" in result

    @pytest.mark.asyncio
    async def test_verify_drug_info_wrong_drug_warning(self, service, mock_ai_service):
        mock_ai_service._call_validator.return_value = (
            '{"status": "warnings", "claims_checked": 2, "warnings": ['
            '{"type": "wrong_drug", "claim": "indication is for diabetes", '
            '"correction": "Metoprolol is a beta-blocker", "severity": "high"}], '
            '"summary": "Wrong drug"}',
            "Cloud AI",
        )
        result = await service.verify_drug_info("Metoprolol", {"indication": "diabetes"})
        assert result["status"] == "warnings"
        assert result["warnings"][0]["type"] == "wrong_drug"

    @pytest.mark.asyncio
    async def test_verify_drug_info_no_validator(self, service, mock_ai_service):
        mock_ai_service._call_validator.return_value = None
        result = await service.verify_drug_info("Metformin", {"indication": "diabetes"})
        assert result["status"] == "unvalidated"
