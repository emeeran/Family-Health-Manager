"""Task-aware provider+model routing — cheapest model meeting an accuracy floor.

For a given task and difficulty, :func:`route` returns an ordered failover list
of ``(provider_id, model)`` pairs: cheapest capable cloud model first (with an
optional preferred family first), Ollama last. :func:`resolve_model_for_task`
returns just the first pick, for streaming tasks that route pre-call and cannot
escalate. :func:`should_escalate` decides whether a low-confidence result should
retry on a stronger model; :func:`record_escalation` memoizes that so
repeated/similar content routes straight to the stronger model next time.

The router is opt-in: callers pass a :class:`TaskType`; when ``AI_ROUTER_ENABLED``
is off (or no task is given) callers keep using ``ordered_providers`` unchanged.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from enum import Enum

from app.core.config import get_settings
from app.core.provider_keys import is_provider_configured
from app.services.ai.model_catalog import (
    MODEL_CATALOG,
    TIERS,
    TIER_RANK,
    ModelSpec,
    ollama_model_spec,
    spec_for,
)

logger = logging.getLogger(__name__)

Difficulty = str  # "easy" | "normal" | "hard"
_DIFFICULTY_TIER: dict[str, str] = {"easy": "fast", "normal": "standard", "hard": "strong"}
_NEXT_DIFFICULTY: dict[str, str] = {"easy": "normal", "normal": "hard", "hard": "hard"}


class TaskType(str, Enum):
    EXTRACTION_VISION = "extraction_vision"
    EXTRACTION_TEXT = "extraction_text"
    VALIDATION = "validation"
    CHAT = "chat"
    REPORT_INSIGHT = "report_insight"


# Per-task accuracy floor/ceiling, modality requirement, and escalation policy.
# escalation=False for streaming tasks (chat, report/insight): they route
# pre-call only and rely on second-model validation as the accuracy backstop.
_TASK_PROFILE: dict[TaskType, dict[str, object]] = {
    TaskType.EXTRACTION_VISION: {
        "min_tier": "standard",
        "max_tier": "strong",
        "modality": "vision",
        "escalation": True,
    },
    TaskType.EXTRACTION_TEXT: {
        "min_tier": "standard",
        "max_tier": "strong",
        "modality": "text",
        "escalation": True,
    },
    TaskType.VALIDATION: {
        "min_tier": "standard",
        "max_tier": "strong",
        "modality": "text",
        "escalation": False,
    },
    TaskType.CHAT: {
        "min_tier": "fast",
        "max_tier": "standard",
        "modality": "text",
        "escalation": False,
    },
    TaskType.REPORT_INSIGHT: {
        "min_tier": "standard",
        "max_tier": "strong",
        "modality": "text",
        "escalation": False,
    },
}

# Numeric confidence for the escalation threshold comparison. Word labels come
# from ``extraction_confidence`` (high/medium/low/none); numbers are pass-through.
_CONF_NUMERIC: dict[str, float] = {"high": 1.0, "medium": 0.5, "low": 0.25, "none": 0.0}

# Memo: content hash -> (escalated difficulty, expires_at). TTL-bounded + sized
# so a one-off hard input doesn't pin a household to the strong tier forever.
_MEMO_TTL = 3600.0
_MEMO_MAX = 512
_ESCALATION_MEMO: OrderedDict[str, tuple[str, float]] = OrderedDict()


def router_enabled() -> bool:
    return bool(get_settings().AI_ROUTER_ENABLED)


def _resolved_tier(task: TaskType, difficulty: Difficulty) -> str:
    """Difficulty tier bumped up to the task floor and capped at its ceiling."""
    prof = _TASK_PROFILE[task]
    rank = TIER_RANK[_DIFFICULTY_TIER.get(difficulty, "standard")]
    rank = max(rank, TIER_RANK[prof["min_tier"]])  # type: ignore[index]
    rank = min(rank, TIER_RANK[prof["max_tier"]])  # type: ignore[index]
    return TIERS[rank]


async def route(
    task: TaskType,
    difficulty: Difficulty,
    config,
    *,
    exclude_family: str = "",
    prefer_family: str = "",
    prompt_tokens: int = 1500,
    completion_tokens: int = 800,
) -> list[tuple[str, str]]:
    """Ordered failover list of ``(provider_id, model)`` for this task+difficulty.

    Cloud models matching the task's modality and resolved tier, on enabled +
    keyed providers, excluding ``exclude_family`` (the generator's family, for
    validation). The household's own configured model is preferred when it
    qualifies; otherwise the cheapest qualifying catalog model for that provider.
    Order: ``prefer_family`` first, then cheapest; Ollama always last (free but
    slow CPU). Returns ``[]`` when nothing qualifies (caller falls back).
    """
    prof = _TASK_PROFILE[task]
    target_tier = _resolved_tier(task, difficulty)
    need_vision = prof["modality"] == "vision"

    enabled = {p.id for p in config.providers if p.enabled}
    configured_model = {p.id: (p.model or "") for p in config.providers}

    keyed: set[str] = set()
    for pid in enabled:
        if pid == "ollama":
            keyed.add(pid)  # local URL; presence in config = available
            continue
        try:
            if await is_provider_configured(pid):
                keyed.add(pid)
        except Exception:  # never let a credential lookup break routing
            logger.debug("provider_keys check failed for %s", pid, exc_info=True)

    def qualifies(spec: ModelSpec) -> bool:
        return (not need_vision or spec.vision_capable) and TIER_RANK[spec.tier] >= TIER_RANK[target_tier]

    cloud_specs: list[ModelSpec] = []
    ollama_model = ""
    for pid in keyed:
        if pid == exclude_family:
            continue
        if pid == "ollama":
            ollama_model = configured_model.get("ollama", "") or "llama3"
            continue
        qualifying = [s for s in MODEL_CATALOG if s.provider == pid and qualifies(s)]
        if not qualifying:
            continue
        # Prefer the household's configured model when it qualifies (user intent).
        cfg = configured_model.get(pid, "")
        cfg_spec = spec_for(pid, cfg) if cfg else None
        chosen = cfg_spec if (cfg_spec and qualifies(cfg_spec)) else min(
            qualifying,
            key=lambda s: (s.cost_estimate(prompt_tokens, completion_tokens), -TIER_RANK[s.tier]),
        )
        cloud_specs.append(chosen)

    def sort_key(spec: ModelSpec) -> tuple[int, float, str, str]:
        prefer_rank = 0 if (prefer_family and spec.provider == prefer_family) else 1
        return (prefer_rank, spec.cost_estimate(prompt_tokens, completion_tokens), spec.provider, spec.model)

    cloud_specs.sort(key=sort_key)
    result = [(s.provider, s.model) for s in cloud_specs]
    # Ollama last — but only when it can serve the task's modality (a text-only
    # local model can't do image extraction).
    if ollama_model and exclude_family != "ollama":
        if not need_vision or ollama_model_spec(ollama_model).vision_capable:
            result.append(("ollama", ollama_model))
    return result


async def resolve_model_for_task(
    task: TaskType,
    difficulty: Difficulty,
    config,
    *,
    exclude_family: str = "",
    prefer_family: str = "",
) -> tuple[str, str] | None:
    """First pick from :func:`route` — for streaming tasks that can't escalate."""
    plan = await route(
        task, difficulty, config, exclude_family=exclude_family, prefer_family=prefer_family
    )
    return plan[0] if plan else None


def should_escalate(task: TaskType, confidence: str | float | None) -> bool:
    """True when a non-streaming task's result confidence is below threshold."""
    if not router_enabled() or not get_settings().AI_ROUTER_ESCALATION_ENABLED:
        return False
    if not _TASK_PROFILE[task]["escalation"]:  # type: ignore[index]
        return False
    if confidence is None:
        return False
    key = str(confidence).lower()
    num = _CONF_NUMERIC.get(key)
    if num is None:
        try:
            num = float(confidence)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    return num < get_settings().AI_ROUTER_CONFIDENCE_THRESHOLD


def next_difficulty(difficulty: Difficulty) -> Difficulty:
    """Bump difficulty for an escalation retry (caps at 'hard')."""
    return _NEXT_DIFFICULTY.get(difficulty, "hard")


# ── escalation memo ─────────────────────────────────────────────────────────


def _memo_key(task: TaskType, content: str) -> str:
    return hashlib.md5(f"{task.value}|{content}".encode()).hexdigest()


def difficulty_for(task: TaskType, content: str, default: Difficulty = "normal") -> Difficulty:
    """Return a memoized escalated difficulty for this content, else ``default``."""
    k = _memo_key(task, content)
    now = time.monotonic()
    hit = _ESCALATION_MEMO.get(k)
    if hit and now < hit[1]:
        _ESCALATION_MEMO.move_to_end(k)
        return hit[0]
    if hit:
        _ESCALATION_MEMO.pop(k, None)
    return default


def record_escalation(task: TaskType, content: str, to_difficulty: Difficulty) -> None:
    """Remember that this content needed ``to_difficulty`` so it routes there directly."""
    k = _memo_key(task, content)
    _ESCALATION_MEMO[k] = (to_difficulty, time.monotonic() + _MEMO_TTL)
    _ESCALATION_MEMO.move_to_end(k)
    while len(_ESCALATION_MEMO) > _MEMO_MAX:
        _ESCALATION_MEMO.popitem(last=False)
