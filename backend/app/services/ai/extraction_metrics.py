"""In-memory per-extraction metrics ring buffer + summary (measurement harness).

Process-wide, best-effort, never raises. Powers ``/ai/extraction-metrics`` so
prompt-trim / fast-model / image-downscale / concurrency changes can be
validated against real per-doc latency, cache hit rate, data rate, and
provider/mime mix instead of guessing (the eval gate that previously blocked
the deferred prompt-trim and fast-model work).

NOT persisted — survives only within a running process (fine for a self-hosted
single-instance app; resets on restart). No locking: ``deque.append`` and
``list()`` are atomic under CPython's GIL and this runs on one async event loop.
"""

from __future__ import annotations

import math
import time
from collections import deque

_MAX_RECORDS = 200
_records: "deque[dict]" = deque(maxlen=_MAX_RECORDS)


def record_extraction(**fields: object) -> None:
    """Record one extraction's metrics. Best-effort — must never raise.

    Fields are free-form; the aggregator understands ``mime``, ``provider``,
    ``cache_hit``, ``pruned``, ``had_data``, and ``elapsed_ms`` (others are kept
    on the record and surface in ``recent``).
    """
    try:
        _records.append({"ts": time.time(), **fields})
    except Exception:  # noqa: BLE001 — metrics must never break extraction
        pass


def clear() -> None:
    """Drop all recorded metrics (used by tests)."""
    _records.clear()


def _percentile(sorted_vals: list[int], p: float) -> int | None:
    """Nearest-rank percentile over a pre-sorted list; None when empty."""
    if not sorted_vals:
        return None
    rank = math.ceil(p * len(sorted_vals))
    return sorted_vals[min(rank, len(sorted_vals)) - 1]


def metrics_summary() -> dict:
    """Aggregate the ring buffer into a snapshot for the debug endpoint."""
    recs = list(_records)
    n = len(recs)
    by_provider: dict[str, int] = {}
    by_mime: dict[str, int] = {}
    cache_hits = 0
    pruned = 0
    had_data = 0
    latencies: list[int] = []
    for r in recs:
        provider = r.get("provider") or "-"
        by_provider[provider] = by_provider.get(provider, 0) + 1
        mime = r.get("mime") or "?"
        by_mime[mime] = by_mime.get(mime, 0) + 1
        if r.get("cache_hit"):
            cache_hits += 1
        if r.get("pruned"):
            pruned += 1
        if r.get("had_data"):
            had_data += 1
        ms = r.get("elapsed_ms")
        if isinstance(ms, (int, float)):
            latencies.append(int(ms))
    latencies.sort()
    return {
        "sample_size": n,
        "cache_hit_rate": round(cache_hits / n, 3) if n else None,
        "pruned_rate": round(pruned / n, 3) if n else None,
        "data_rate": round(had_data / n, 3) if n else None,
        "by_provider": by_provider,
        "by_mime": by_mime,
        "latency_ms": {
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": latencies[-1] if latencies else None,
        },
        "recent": list(recs[-10:]),
    }
