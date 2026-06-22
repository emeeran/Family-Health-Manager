"""SSE stream disconnect handling.

An abandoned client must not keep the upstream (CPU-only Ollama) generating tokens
nobody will read. make_sse_stream polls request.is_disconnected() and, on
disconnect, breaks the loop and closes the source so the producer is cancelled.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.core.sse import make_sse_stream

pytestmark = pytest.mark.asyncio


class _FakeRequest:
    """Reports disconnected once ``is_disconnected`` has been polled ``threshold`` times."""

    def __init__(self, threshold: int = 2):
        self._n = 0
        self._threshold = threshold

    async def is_disconnected(self) -> bool:
        self._n += 1
        return self._n >= self._threshold


async def test_make_sse_stream_stops_and_closes_source_on_disconnect():
    closed = {"v": False}

    async def source():
        try:
            for i in range(5):
                yield json.dumps({"stage": "token", "i": i})
        finally:
            closed["v"] = True

    db = AsyncMock()
    response = make_sse_stream(source(), db, _FakeRequest(threshold=2))

    out = []
    async for chunk in response.body_iterator:
        out.append(chunk)

    # Only the first token is forwarded before the 2nd is_disconnected() poll
    # returns True; the source is then closed (its finally ran) — i.e. the
    # upstream was cancelled instead of draining all 5 tokens.
    assert len(out) == 1
    assert closed["v"] is True


async def test_make_sse_stream_drains_fully_when_connected():
    async def source():
        for i in range(3):
            yield json.dumps({"stage": "token", "i": i})

    db = AsyncMock()
    response = make_sse_stream(source(), db, request=None)

    out = []
    async for chunk in response.body_iterator:
        out.append(chunk)

    assert len(out) == 3
