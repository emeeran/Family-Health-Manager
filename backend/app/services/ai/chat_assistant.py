"""Conversation-history helper for the chat assistant.

Chat and chat streaming live on the ``AIService`` facade
(``app/services/ai/__init__.py``); this module holds the conversation-history
lookup (with a short-lived cache) that the facade delegates to.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Message, MessageRole

logger = logging.getLogger(__name__)

# Short-lived cache for conversation history — avoids re-querying on rapid back-and-forth
_history_cache: dict[str, tuple[str, float]] = {}
_HISTORY_TTL = 120.0  # 2 minutes


async def _get_conversation_history(
    db: AsyncSession, conversation_id: UUID, limit: int = 10
) -> str:
    """Get recent conversation history, with short-lived cache."""
    import time

    cache_key = str(conversation_id)
    cached = _history_cache.get(cache_key)
    if cached:
        value, ts = cached
        if time.monotonic() - ts < _HISTORY_TTL:
            return value
        _history_cache.pop(cache_key, None)

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    history = ""
    for msg in messages:
        role = "User" if msg.role == MessageRole.USER else "Assistant"
        history += f"{role}: {msg.content}\n"

    _history_cache[cache_key] = (history, time.monotonic())
    return history
