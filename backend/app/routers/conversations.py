"""Conversation router."""
import asyncio
import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.config import get_settings
from app.core.database import get_db, SessionLocal
from app.core.deps import get_household_from_token
from app.core.sse import make_sse_stream
from app.services.ai_service import AIService
from app.services.verification_service import VerificationService
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.schemas.message import MessageCreate
from app.models.base import Household, Conversation, Message

router = APIRouter(prefix="/conversations", tags=["Conversations"])
logger = logging.getLogger(__name__)
settings = get_settings()


def _verification_to_dict(v):
    """Convert a ResponseVerification ORM object to a plain dict."""
    warnings = None
    if v.warnings_json:
        try:
            warnings = json.loads(v.warnings_json)
        except (json.JSONDecodeError, ValueError):
            warnings = None
    return {
        "status": v.status,
        "claims_checked": v.claims_checked,
        "verifier_provider": v.verifier_provider,
        "summary": v.summary,
        "warnings": warnings,
        "verified_at": v.verified_at,
    }


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations."""
    result = await db.execute(
        select(Conversation).where(Conversation.household_id == household.id)
    )
    convs = list(result.scalars().all())
    return [
        {
            "id": c.id,
            "household_id": c.household_id,
            "family_member_id": c.family_member_id,
            "scope": c.scope,
            "title": c.title,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in convs
    ]


@router.post("", status_code=201, response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation."""
    conversation = Conversation(
        household_id=household.id,
        family_member_id=request.family_member_id,
        scope=request.scope,
        title=request.title,
    )
    db.add(conversation)
    await db.flush()
    return {
        "id": conversation.id,
        "household_id": conversation.household_id,
        "family_member_id": conversation.family_member_id,
        "scope": conversation.scope,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation with message history."""
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.household_id == household.id,
        )
        .options(
            selectinload(Conversation.messages).selectinload(
                Message.verification
            )
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = sorted(conversation.messages, key=lambda m: m.created_at)

    msg_dicts = []
    for m in messages:
        d = {
            "id": m.id,
            "conversation_id": m.conversation_id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
        }
        if m.verification:
            d["verification"] = _verification_to_dict(m.verification)
        msg_dicts.append(d)

    return {
        "conversation": {
            "id": conversation.id,
            "household_id": conversation.household_id,
            "family_member_id": conversation.family_member_id,
            "scope": conversation.scope,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        },
        "messages": msg_dicts,
    }


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation."""
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.household_id == household.id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Detach orphaned FK references before cascade-deleting messages
    message_ids = [m.id for m in conversation.messages] if conversation.messages else []

    if message_ids:
        from app.models.base import AIInsight
        from app.models.verification import ResponseVerification

        await db.execute(
            AIInsight.__table__.update()
            .where(AIInsight.conversation_id == conversation_id)
            .values(conversation_id=None)
        )
        await db.execute(
            ResponseVerification.__table__.delete()
            .where(ResponseVerification.message_id.in_(message_ids))
        )

    await db.delete(conversation)
    await db.flush()


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: UUID,
    body: dict | None = None,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Update conversation properties (e.g., rename title)."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.household_id == household.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if body and "title" in body and body["title"]:
        conversation.title = str(body["title"]).strip()[:200]
        await db.flush()

    return {"id": str(conversation.id), "title": conversation.title}


@router.post("/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: UUID,
    request: MessageCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Send a message and stream the AI response token-by-token via SSE."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.household_id == household.id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    service = AIService(db, household_id=household.id)
    stream = service.chat_stream(
        conversation_id=conversation_id,
        user_message=request.content,
        member_id=conversation.family_member_id,
        household_id=household.id,
    )

    response = make_sse_stream(stream, db)

    # Save the original stream BEFORE wrapping to avoid self-reference
    original_stream = response.body_iterator

    # Wrap to add post-stream verification
    class VerificationSSEWrapper:
        """Wraps SSE stream to fire verification after completion."""

        def __init__(self, stream):
            self._stream = stream

        async def __aiter__(self):
            provider = None
            health_context = None
            message_id = None
            async for chunk in self._stream:
                # Track the complete event for verification
                if chunk.startswith("data: "):
                    try:
                        data = json.loads(chunk[6:].strip())
                        if data.get("stage") == "complete":
                            provider = data.get("provider")
                            health_context = data.get("health_context")
                            msg = data.get("assistant_message", {})
                            message_id = msg.get("id")
                    except (json.JSONDecodeError, AttributeError):
                        pass
                yield chunk

            # Fire verification in background with its own DB session
            if settings.AI_VERIFICATION_ENABLED and health_context and message_id:
                async def _run_verification():
                    verify_db = SessionLocal()
                    try:
                        verify_service = AIService(verify_db, household_id=household.id)
                        verification_svc = VerificationService(verify_db, verify_service)
                        await verification_svc.verify(
                            question=request.content,
                            ai_response="",  # already in DB
                            health_context=health_context,
                            original_provider=provider or "",
                            message_id=UUID(message_id),
                        )
                        await verify_db.commit()
                    except Exception as exc:
                        await verify_db.rollback()
                        logger.info("Post-stream verification skipped: %s", exc)
                    finally:
                        await verify_db.close()

                try:
                    asyncio.ensure_future(_run_verification())
                except Exception as exc:
                    logger.info("Post-stream verification spawn failed: %s", exc)

    response.body_iterator = VerificationSSEWrapper(original_stream)
    return response


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: UUID,
    request: MessageCreate,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Send a message in a conversation."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.household_id == household.id,
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    service = AIService(db, household_id=household.id)

    try:
        user_msg, assistant_msg, provider, health_context = await service.chat(
            conversation_id=conversation_id,
            user_message=request.content,
            member_id=conversation.family_member_id,
            household_id=household.id,
        )
    except Exception:
        logger.exception("AI chat failed for conversation %s", conversation_id)
        raise HTTPException(status_code=500, detail="AI service unavailable")

    verification_data = None

    if settings.AI_VERIFICATION_ENABLED and health_context:
        try:
            verification_svc = VerificationService(db, service)
            verification = await asyncio.wait_for(
                verification_svc.verify(
                    question=request.content,
                    ai_response=assistant_msg.content,
                    health_context=health_context,
                    original_provider=provider,
                    message_id=assistant_msg.id,
                ),
                timeout=3.0,
            )
            verification_data = _verification_to_dict(verification)
        except asyncio.TimeoutError:
            # Verification didn't finish in time — frontend will poll
            logger.info("Verification timed out for message %s", assistant_msg.id)
        except Exception as exc:
            logger.warning("Verification error for message %s: %s", assistant_msg.id, exc)

    resp = {
        "user_message": {
            "id": user_msg.id,
            "conversation_id": user_msg.conversation_id,
            "role": user_msg.role,
            "content": user_msg.content,
            "created_at": user_msg.created_at,
        },
        "assistant_message": {
            "id": assistant_msg.id,
            "conversation_id": assistant_msg.conversation_id,
            "role": assistant_msg.role,
            "content": assistant_msg.content,
            "created_at": assistant_msg.created_at,
            "disclaimer": "This is not medical advice. Consult a healthcare professional.",
        },
    }
    if verification_data:
        resp["verification"] = verification_data
    return resp


@router.get("/{conversation_id}/messages/{message_id}/verification")
async def get_message_verification(
    conversation_id: UUID,
    message_id: UUID,
    household: Household = Depends(get_household_from_token),
    db: AsyncSession = Depends(get_db),
):
    """Poll for verification result of a specific message."""
    from app.models.verification import ResponseVerification

    # Verify the conversation belongs to this household
    conv = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.household_id == household.id,
        )
    )
    if not conv.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(ResponseVerification).where(
            ResponseVerification.message_id == message_id
        )
    )
    verification = result.scalar_one_or_none()

    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")

    return _verification_to_dict(verification)
