"""SSE (Server-Sent Events) utilities."""

import json
import logging
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def make_sse_stream(
    source: AsyncIterator[str],
    db: AsyncSession,
    request: Request | None = None,
) -> StreamingResponse:
    """Wrap an async iterator of JSON strings into an SSE StreamingResponse.

    Commits the DB session on success, rolls back on error.
    Automatically fires insight verification when a complete event is seen.

    When ``request`` is supplied the stream polls
    ``request.is_disconnected()`` and stops early if the client goes away,
    then closes the upstream source so an abandoned browser tab doesn't keep a
    CPU-only Ollama worker busy for minutes after the user navigates off.
    """

    async def event_stream():
        insight_id: str | None = None
        member_id: str | None = None
        try:
            async for data in source:
                if request is not None and await request.is_disconnected():
                    logger.info("Client disconnected from SSE stream; cancelling upstream")
                    break
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

                    spawn_insight_verification_task(
                        UUID(insight_id), "streaming insight", member_id=member_id
                    )
                except Exception:
                    logger.debug("Post-stream verification skipped")
        except Exception as exc:
            await db.rollback()
            logger.error("Insight stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'stage': 'error', 'message': 'An error occurred during streaming'})}\n\n"
        finally:
            # On early stop (client disconnect) close the upstream producer so we
            # don't keep generating tokens nobody will read. On normal completion
            # the source is already exhausted and aclose() is a no-op.
            aclose = getattr(source, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:
                    logger.debug("Source aclose after SSE stream failed", exc_info=True)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
