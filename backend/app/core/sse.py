"""SSE (Server-Sent Events) utilities."""
import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def make_sse_stream(
    source: AsyncIterator[str],
    db: AsyncSession,
) -> StreamingResponse:
    """Wrap an async iterator of JSON strings into an SSE StreamingResponse.

    Commits the DB session on success, rolls back on error.
    Automatically fires insight verification when a complete event is seen.
    """
    async def event_stream():
        insight_id: str | None = None
        member_id: str | None = None
        try:
            async for data in source:
                # Detect completed insights to trigger verification
                if insight_id is None:
                    try:
                        parsed = json.loads(data)
                        if parsed.get("stage") == "complete" and parsed.get("insight_id"):
                            insight_id = parsed["insight_id"]
                            member_id = parsed.get("member_id")
                    except (json.JSONDecodeError, AttributeError):
                        pass
                yield f"data: {data}\n\n"
            # Flush pending changes; get_db dependency will handle the final commit+close
            await db.flush()
            # Fire-and-forget verification after flush
            if insight_id:
                try:
                    from app.services.insight_service import spawn_insight_verification_task
                    spawn_insight_verification_task(UUID(insight_id), "streaming insight", member_id=member_id)
                except Exception:
                    logger.debug("Post-stream verification skipped")
        except Exception as exc:
            await db.rollback()
            logger.error("Insight stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'stage': 'error', 'message': 'An error occurred during streaming'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
