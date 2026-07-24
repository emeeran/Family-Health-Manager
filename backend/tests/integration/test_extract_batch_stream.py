"""Streaming batch extraction endpoint (``/extract-batch/stream``).

Verifies the SSE event sequence (start → file_complete×N → done), the 15s
heartbeat that keeps the long CPU extraction alive, per-file error isolation,
and deadlock-freedom when every file fails. The AI layer is mocked so this
exercises the streaming wiring, not the model.
"""

import asyncio
import json
from datetime import date

import pytest

from app.models.base import RecordType
from app.schemas.health_record import ExtractedFields
from app.services.ai import AIService
from app.services.ai.document_extractor import ExtractionResult
from app.services.verification_service import VerificationService

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Batch",
    "last_name": "Patient",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}

# Minimal PDF-shaped payload: passes magic-byte validation without a real PDF.
PDF_BYTES = b"%PDF-1.4\n%batch stream test\n" + b"x" * 200


async def _create_member(auth_client) -> str:
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


def _data_events(resp_lines):
    """Pull parsed JSON payloads from the SSE `data:` lines (skips heartbeats)."""
    events = []
    for line in resp_lines:
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


def _files_payload(*names: str):
    return [("files", (name, PDF_BYTES, "application/pdf")) for name in names]


@pytest.fixture
def stub_verification(monkeypatch):
    """Avoid real AI provider calls during verification in tests."""

    async def fake_verify(self, data, original_provider=""):
        return {"status": "verified", "verifier_provider": "test"}

    monkeypatch.setattr(VerificationService, "verify_extraction", fake_verify)


async def test_batch_stream_emits_start_per_file_then_done(
    auth_client, monkeypatch, stub_verification
):
    """The stream opens with start, emits one file_complete per file, ends done."""

    async def fake_extract(self, file_path, mime_type, content_hash=None):
        return ExtractionResult(
            extracted=ExtractedFields(
                record_type=RecordType.DOCTOR_VISIT,
                record_date=date(2024, 1, 15),
                diagnosis="Type 2 Diabetes",
            ),
            transcription="raw transcription",
        )

    monkeypatch.setattr(AIService, "extract_medical_data", fake_extract)
    member_id = await _create_member(auth_client)

    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract-batch/stream",
        files=_files_payload("a.pdf", "b.pdf"),
    ) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines()]

    events = _data_events(lines)
    stages = [e.get("stage") for e in events]
    assert stages[0] == "start"
    assert stages[-1] == "done"

    file_events = [e for e in events if e.get("stage") == "file_complete"]
    assert len(file_events) == 2
    # Every file_complete carries a staging id + extracted diagnosis, and an
    # upload-order index.
    for e in file_events:
        assert e["total"] == 2
        assert e["index"] in (0, 1)
        assert e["item"]["staging_file_id"]
        assert e["item"]["extracted"]["diagnosis"] == "Type 2 Diabetes"
        assert e["item"]["verification"]["status"] == "verified"
    assert {e["index"] for e in file_events} == {0, 1}


async def test_batch_stream_verifies_high_confidence_extractions(
    auth_client, monkeypatch, stub_verification
):
    """High-coverage extractions are verified too (verify-all). The stubbed
    verify_extraction returns 'verified', so seeing 'verified' (not a heuristic
    'auto_verified') proves the second-model pass actually ran.
    """

    async def fake_extract(self, file_path, mime_type, content_hash=None):
        # record_type(1)+date(1)+diagnosis(1)+chief_complaint(1)+provider(1)+
        # prescriptions(2) = 7 → extraction_confidence == "high".
        return ExtractionResult(
            extracted=ExtractedFields(
                record_type=RecordType.DOCTOR_VISIT,
                record_date=date(2024, 1, 15),
                diagnosis="Type 2 Diabetes",
                chief_complaint="fatigue",
                provider_name="Dr. Mehta",
                prescriptions=[{"medicine": "Metformin 500mg"}],
            ),
            transcription="raw",
        )

    monkeypatch.setattr(AIService, "extract_medical_data", fake_extract)
    member_id = await _create_member(auth_client)

    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract-batch/stream",
        files=_files_payload("a.pdf"),
    ) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines()]

    file_events = [e for e in _data_events(lines) if e.get("stage") == "file_complete"]
    assert len(file_events) == 1
    assert file_events[0]["item"]["verification"]["status"] == "verified"


async def test_batch_stream_heartbeats_during_long_extract(
    auth_client, monkeypatch, stub_verification
):
    """A slow extraction yields `: keepalive` lines that keep the connection alive."""

    async def slow_extract(self, file_path, mime_type, content_hash=None):
        await asyncio.sleep(16)  # > 15s heartbeat interval
        return ExtractionResult(extracted=ExtractedFields(diagnosis="ok"))

    monkeypatch.setattr(AIService, "extract_medical_data", slow_extract)
    member_id = await _create_member(auth_client)

    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract-batch/stream",
        files=_files_payload("a.pdf", "b.pdf"),
    ) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines()]

    # Heartbeat comment lines have no `data:` prefix — assert at least one fired.
    assert any(": keepalive" in line for line in lines)
    stages = [e.get("stage") for e in _data_events(lines)]
    assert stages[-1] == "done"


async def test_batch_stream_surfaces_per_file_error(auth_client, monkeypatch, stub_verification):
    """One file failing does not kill the stream; both file_complete events fire."""

    calls = {"n": 0}

    async def flaky_extract(self, file_path, mime_type, content_hash=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model down for one file")
        return ExtractionResult(extracted=ExtractedFields(diagnosis="recovered"))

    monkeypatch.setattr(AIService, "extract_medical_data", flaky_extract)
    member_id = await _create_member(auth_client)

    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract-batch/stream",
        files=_files_payload("a.pdf", "b.pdf"),
    ) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines()]

    file_events = [e for e in _data_events(lines) if e.get("stage") == "file_complete"]
    assert len(file_events) == 2  # one error item + one success item
    # Discriminate by `error`: error-items still carry an (empty) ExtractedFields.
    errors = [e for e in file_events if e["item"].get("error")]
    successes = [e for e in file_events if not e["item"].get("error")]
    assert len(errors) == 1
    assert len(successes) == 1
    assert "model down" in errors[0]["item"]["error"]
    assert successes[0]["item"]["extracted"]["diagnosis"] == "recovered"


async def test_batch_stream_all_fail_does_not_deadlock(auth_client, monkeypatch, stub_verification):
    """If every producer raises, the stream still reaches done (no hang)."""

    async def failing_extract(self, file_path, mime_type, content_hash=None):
        raise RuntimeError("everything is broken")

    monkeypatch.setattr(AIService, "extract_medical_data", failing_extract)
    member_id = await _create_member(auth_client)

    def _drain():
        async def go():
            async with auth_client.stream(
                "POST",
                f"/api/v1/members/{member_id}/records/extract-batch/stream",
                files=_files_payload("a.pdf", "b.pdf"),
            ) as resp:
                assert resp.status_code == 200
                return [line async for line in resp.aiter_lines()]

        return go()

    lines = await asyncio.wait_for(_drain(), timeout=10)
    events = _data_events(lines)
    stages = [e.get("stage") for e in events]
    assert stages[-1] == "done"
    file_events = [e for e in events if e.get("stage") == "file_complete"]
    assert len(file_events) == 2
    assert all(e["item"].get("error") for e in file_events)
