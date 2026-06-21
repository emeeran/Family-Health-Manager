"""Cross-household authorization regression tests.

Read endpoints that take both a path member/conversation id and a secondary
resource id (record_id, message_id) must verify the secondary id belongs to the
caller's household. These tests prove the record-insight and
message-verification endpoints no longer leak across households, while
same-household access still works.
"""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models.base import (
    AIInsight,
    ConversationScope,
    FamilyMember,
    HealthRecord,  # noqa: F401  (import keeps model registry side effects explicit)
    MessageRole,
)
from app.models.conversation import Conversation, Message
from app.models.verification import ResponseVerification

pytestmark = pytest.mark.asyncio


MEMBER_PAYLOAD = {
    "first_name": "Authz",
    "last_name": "Patient",
    "date_of_birth": "1990-01-01",
    "gender": "male",
    "relationship": "self",
}

RECORD_PAYLOAD = {
    "record_type": "doctor_visit",
    "record_date": "2025-01-15",
    "clinical_data": "Routine visit",
    "diagnosis": "Healthy",
}


async def _token(client, username: str, password: str = "TestP@ss123") -> str:
    """Register+login a fresh user on the shared client; return its access token."""
    resp = await client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def _create_member(client, token: str) -> str:
    resp = await client.post("/api/v1/members", json=MEMBER_PAYLOAD, params={"token": token})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _household_of(db_session, member_id: str):
    row = await db_session.execute(select(FamilyMember).where(FamilyMember.id == UUID(member_id)))
    return row.scalar_one().household_id


async def test_record_insight_not_leaked_across_households(auth_client, db_session):
    """A guessed record_id must not return another household's AI insight."""
    token_a = auth_client.params["token"]
    token_b = await _token(auth_client, "householdB_user")

    member_a = await _create_member(auth_client, token_a)
    member_b = await _create_member(auth_client, token_b)

    # Household A owns a record with a generated insight.
    create = await auth_client.post(
        f"/api/v1/members/{member_a}/records", json=RECORD_PAYLOAD, params={"token": token_a}
    )
    assert create.status_code == 201
    record_a = create.json()["id"]

    db_session.add(
        AIInsight(
            health_record_id=UUID(record_a),
            prompt="prompt-a",
            response="SECRET-insight-A",
            provider_used="test",
            generated_at=datetime.now(timezone.utc),
            verification_status="verified",
            verification_verifier="test",
            verification_summary="ok",
            verification_at=datetime.now(timezone.utc),
        )
    )
    await db_session.flush()

    # Positive control: owner (A) can read the insight.
    own = await auth_client.get(
        f"/api/v1/members/{member_a}/records/{record_a}/insight", params={"token": token_a}
    )
    assert own.status_code == 200
    assert own.json()["insight"]["response"] == "SECRET-insight-A"

    # Negative: B using its own member_id + A's record_id → 404, not the insight.
    leak = await auth_client.get(
        f"/api/v1/members/{member_b}/records/{record_a}/insight", params={"token": token_b}
    )
    assert leak.status_code == 404

    leak_ver = await auth_client.get(
        f"/api/v1/members/{member_b}/records/{record_a}/insight/verification",
        params={"token": token_b},
    )
    assert leak_ver.status_code == 404


async def test_message_verification_not_leaked_across_conversations(auth_client, db_session):
    """A caller's own conversation_id + a victim's message_id must 404."""
    token_a = auth_client.params["token"]
    token_b = await _token(auth_client, "convB_user")

    member_a = await _create_member(auth_client, token_a)
    member_b = await _create_member(auth_client, token_b)
    hh_a = await _household_of(db_session, member_a)
    hh_b = await _household_of(db_session, member_b)

    # Household A: a conversation with a message + verification.
    conv_a = Conversation(household_id=hh_a, scope=ConversationScope.GENERAL)
    db_session.add(conv_a)
    await db_session.flush()
    msg_a = Message(conversation_id=conv_a.id, role=MessageRole.USER, content="SECRET-msg-A")
    db_session.add(msg_a)
    await db_session.flush()
    db_session.add(
        ResponseVerification(
            message_id=msg_a.id,
            status="verified",
            verifier_provider="test",
            summary="ok",
        )
    )
    await db_session.flush()

    # Household B: its own conversation.
    conv_b = Conversation(household_id=hh_b, scope=ConversationScope.GENERAL)
    db_session.add(conv_b)
    await db_session.flush()

    # Positive control: owner (A) reads its message verification.
    own = await auth_client.get(
        f"/api/v1/conversations/{conv_a.id}/messages/{msg_a.id}/verification",
        params={"token": token_a},
    )
    assert own.status_code == 200

    # Negative: B's conversation + A's message_id → 404.
    leak = await auth_client.get(
        f"/api/v1/conversations/{conv_b.id}/messages/{msg_a.id}/verification",
        params={"token": token_b},
    )
    assert leak.status_code == 404
