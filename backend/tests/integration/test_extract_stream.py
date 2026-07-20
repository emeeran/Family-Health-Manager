"""Phase 2 — SSE streaming extraction endpoint.

Verifies the real event sequence (secured → extracting → complete) and that
extraction failures surface as an error event instead of crashing the stream.
The AI layer is mocked so this exercises the streaming wiring, not the model.
"""

import json
from datetime import date
from io import BytesIO

import pytest
from fastapi import UploadFile

from app.core.storage import save_staged_secured
from app.models.base import RecordType
from app.schemas.health_record import ExtractedFields
from app.services.ai import AIService
from app.services.ai.document_extractor import ExtractionResult

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Stream",
    "last_name": "Patient",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}

# Minimal PDF-shaped payload: passes magic-byte validation without a real PDF.
PDF_BYTES = b"%PDF-1.4\n%phase2 streaming test\n" + b"x" * 200


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


async def test_extract_stream_emits_secured_then_complete(auth_client, monkeypatch):
    """Upload is acked instantly (secured); the full result follows (complete)."""

    async def fake_extract(self, file_path, mime_type, content_hash=None, on_progress=None):
        return ExtractionResult(
            extracted=ExtractedFields(
                record_type=RecordType.DOCTOR_VISIT,
                record_date=date(2024, 1, 15),
                provider_name="Test Clinic",
                diagnosis="Type 2 Diabetes",
                chief_complaint="Follow-up",
                prescriptions=[{"medicine": "Metformin 500mg"}],
            ),
            transcription="raw transcription",
        )

    monkeypatch.setattr(AIService, "extract_medical_data", fake_extract)
    member_id = await _create_member(auth_client)

    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract/stream",
        files={"file": ("scan.pdf", PDF_BYTES, "application/pdf")},
    ) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines()]

    events = _data_events(lines)
    stages = [e.get("stage") for e in events]
    assert stages[0] == "secured"
    assert "extracting" in stages
    assert stages[-1] == "complete"

    secured = events[0]
    assert secured["staging_file_id"]
    assert len(secured["content_hash"]) == 64  # SHA-256 hex

    complete = events[-1]
    assert complete["staging_file_id"] == secured["staging_file_id"]
    assert complete["extracted"]["diagnosis"] == "Type 2 Diabetes"
    assert complete["transcription"] == "raw transcription"
    assert complete["confidence"] == "high"


async def test_extract_stream_surfaces_extraction_error(auth_client, monkeypatch):
    """An extraction failure becomes an error event, not a dead stream."""

    async def fake_extract(self, file_path, mime_type, content_hash=None, on_progress=None):
        raise RuntimeError("model down")

    monkeypatch.setattr(AIService, "extract_medical_data", fake_extract)
    member_id = await _create_member(auth_client)

    async with auth_client.stream(
        "POST",
        f"/api/v1/members/{member_id}/records/extract/stream",
        files={"file": ("scan.pdf", PDF_BYTES, "application/pdf")},
    ) as resp:
        assert resp.status_code == 200
        lines = [line async for line in resp.aiter_lines()]

    stages = [e.get("stage") for e in _data_events(lines)]
    assert stages[0] == "secured"
    assert stages[-1] == "error"


async def test_get_staging_file_serves_decrypted_original(auth_client):
    """The "View original" endpoint streams the staged file decrypted, inline."""
    body = b"%PDF-1.4 original preview content for the fly-out"
    upload = UploadFile(
        file=BytesIO(body),
        filename="scan.pdf",
        headers={"content-type": "application/pdf"},
    )
    _staged, staging_id, _hash = await save_staged_secured(upload)
    member_id = await _create_member(auth_client)

    resp = await auth_client.get(f"/api/v1/members/{member_id}/records/staging/{staging_id}")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == body  # decrypted plaintext, not the on-disk ciphertext
    assert "inline" in resp.headers.get("content-disposition", "")


async def test_get_staging_file_rejects_traversal(auth_client):
    """A staging file id that escapes the staging dir is rejected."""
    member_id = await _create_member(auth_client)
    resp = await auth_client.get(
        f"/api/v1/members/{member_id}/records/staging/..%2F..%2Fetc%2Fpasswd"
    )
    assert resp.status_code in (400, 404)
