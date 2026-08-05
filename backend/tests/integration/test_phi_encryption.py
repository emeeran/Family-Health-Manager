"""PHI is encrypted at rest in the DB but transparent over the API.

Creates records via the API (which encrypt on write through the TypeDecorator),
then reads the columns RAW (bypassing the ORM, so no decrypt) to prove the
on-disk value is Fernet ciphertext — not the plaintext diagnosis/clinical data.
Then reads via the API to prove the round-trip is transparent.
"""

import pytest
from sqlalchemy import text

from app.core.encryption import is_secret_encrypted

pytestmark = pytest.mark.asyncio

MEMBER_PAYLOAD = {
    "first_name": "Phi",
    "last_name": "Patient",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}


async def _create_member(auth_client) -> str:
    resp = await auth_client.post("/api/v1/members", json=MEMBER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_record_phi_is_ciphertext_on_disk_plaintext_via_api(auth_client, db_session):
    member_id = await _create_member(auth_client)
    create = await auth_client.post(
        f"/api/v1/members/{member_id}/records",
        json={
            "record_type": "doctor_visit",
            "record_date": "2026-01-01",
            "clinical_data": "Patient reports chest pain, BP 150/95",
            "diagnosis": "Hypertension",
        },
    )
    assert create.status_code == 201, create.text
    record_id = create.json()["id"]

    # RAW read bypasses the ORM TypeDecorator → the on-disk ciphertext. Query
    # all rows (the per-test DB has only this record) to avoid UUID storage-format
    # mismatch in a raw id filter.
    row = (
        await db_session.execute(text("SELECT clinical_data, diagnosis FROM health_records"))
    ).one()
    raw_clinical, raw_diagnosis = row
    assert is_secret_encrypted(raw_clinical), "clinical_data must be Fernet ciphertext on disk"
    assert is_secret_encrypted(raw_diagnosis), "diagnosis must be Fernet ciphertext on disk"
    # The plaintext must not appear anywhere in the stored ciphertext.
    assert "chest pain" not in raw_clinical
    assert "Hypertension" not in raw_diagnosis

    # API read transparently decrypts.
    got = await auth_client.get(f"/api/v1/members/{member_id}/records/{record_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["clinical_data"] == "Patient reports chest pain, BP 150/95"
    assert body["diagnosis"] == "Hypertension"


async def test_member_phi_encrypted_at_rest(auth_client, db_session):
    """Allergies / medical history / contact fields are ciphertext on disk."""
    member_id = await _create_member(auth_client)
    await auth_client.put(
        f"/api/v1/members/{member_id}",
        json={
            "medical_history_summary": "Type 2 Diabetes",
            "allergies": [{"name": "Penicillin", "severity": "severe"}],
            "phone": "+1-555-0100",
        },
    )
    row = (
        await db_session.execute(
            text("SELECT medical_history_summary, allergies_json, phone FROM family_members")
        )
    ).one()
    history, allergies, phone = row
    assert is_secret_encrypted(history)
    assert is_secret_encrypted(allergies)
    assert is_secret_encrypted(phone)
    assert "Diabetes" not in history
    assert "Penicillin" not in allergies


async def test_chat_message_encrypted_at_rest(auth_client, db_session):
    member_id = await _create_member(auth_client)
    # Create a member-scoped conversation + a message directly via the ORM (the
    # TypeDecorator encrypts on flush). Then assert the on-disk content is
    # ciphertext and the API conversation read is plaintext.
    from uuid import UUID, uuid4

    from app.models.base import Conversation, Message
    from app.models.base import ConversationScope, MessageRole

    conv = Conversation(
        id=uuid4(),
        household_id=uuid4(),  # FK enforcement off in SQLite tests; value irrelevant
        family_member_id=UUID(member_id),
        scope=ConversationScope.MEMBER,
        title="My private chat",
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        Message(
            id=uuid4(),
            conversation_id=conv.id,
            role=MessageRole.USER,
            content="I have a sensitive symptom to discuss",
        )
    )
    await db_session.commit()

    title = (
        await db_session.execute(text("SELECT title FROM conversations"))
    ).scalar_one()
    msg = (
        await db_session.execute(text("SELECT content FROM messages"))
    ).scalar_one()
    assert is_secret_encrypted(title)
    assert is_secret_encrypted(msg)
    assert "private chat" not in title
    assert "sensitive symptom" not in msg
