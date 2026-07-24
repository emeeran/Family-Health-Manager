"""Model catalog: capability tier, modalities, and pricing for task routing.

The router (:mod:`app.services.ai.task_router`) uses this to pick, per task and
difficulty, the cheapest model that still meets the task's accuracy floor.

**Tier** (the primary signal): ``fast`` < ``standard`` < ``strong``. ``fast`` covers
small/cheap models (8B-class, nano) suitable for easy chat/parse work;
``standard`` covers capable workhorses (70B, Gemini Flash, gpt-mini) that meet
the accuracy floor for extraction / validation / reports; ``strong`` covers
frontier models (Gemini Pro, gpt-4o) reserved for the hard tail via escalation.

**Price** is the cost *tiebreaker* (USD per 1M tokens). Groq and Gemini have free
tiers (``$0``); OpenAI/OpenRouter have published rates. A stale price rarely
misroutes across tiers — it only reorders within one. OpenRouter prices are
refreshable at runtime via :mod:`app.services.ai.model_fetcher`.

Ollama models are free-text, so they aren't enumerated here; see
:func:`ollama_model_spec`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Ordered low → high capability. Index = rank used for floor comparisons.
TIERS: tuple[str, ...] = ("fast", "standard", "strong")
TIER_RANK: dict[str, int] = {tier: i for i, tier in enumerate(TIERS)}

TEXT = frozenset({"text"})
TEXT_VISION = frozenset({"text", "vision"})


@dataclass(frozen=True)
class ModelSpec:
    """One routable model: provider + model id + tier + modalities + price."""

    provider: str
    model: str
    tier: str  # fast | standard | strong
    modalities: frozenset[str]  # TEXT or TEXT_VISION
    prompt_price: float  # USD / 1M input tokens (0.0 = free/unknown)
    completion_price: float  # USD / 1M output tokens
    context: int = 0  # max context tokens (0 = unknown)

    @property
    def vision_capable(self) -> bool:
        return "vision" in self.modalities

    def cost_estimate(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Approximate USD for one call of this size."""
        return (
            self.prompt_price * prompt_tokens / 1_000_000
            + self.completion_price * completion_tokens / 1_000_000
        )


# Best-known USD/1M-token prices at catalog authoring. Free tiers are $0.
# Fictional/future model ids in this project carry plausible estimates — the
# comment marks them so a maintainer knows to verify.
MODEL_CATALOG: tuple[ModelSpec, ...] = (
    # ── Groq (free tier → $0; tier by parameter count) ──
    ModelSpec("groq", "llama-3.3-70b-versatile", "standard", TEXT, 0.0, 0.0, 131072),
    ModelSpec("groq", "llama-3.1-8b-instant", "fast", TEXT, 0.0, 0.0, 131072),
    # ── Google Gemini (free-tier $0; Flash=standard-capable, Pro=strong; all vision) ──
    ModelSpec("gemini", "gemini-2.5-flash", "standard", TEXT_VISION, 0.0, 0.0, 1_048_576),
    ModelSpec("gemini", "gemini-2.5-pro", "strong", TEXT_VISION, 1.25, 10.0, 2_097_152),
    ModelSpec("gemini", "gemini-2.0-flash", "standard", TEXT_VISION, 0.0, 0.0, 1_048_576),
    # ── OpenAI (published rates) ──
    ModelSpec("openai", "gpt-5.4-mini", "standard", TEXT_VISION, 0.40, 1.60, 131072),  # estimate
    ModelSpec("openai", "gpt-5.4-nano", "fast", TEXT, 0.10, 0.40, 131072),  # estimate
    ModelSpec("openai", "gpt-4o", "strong", TEXT_VISION, 2.50, 10.0, 131072),
    ModelSpec("openai", "gpt-4o-mini", "standard", TEXT_VISION, 0.15, 0.60, 131072),
    # ── OpenRouter (prices refreshable via model_fetcher; defaults shown) ──
    ModelSpec("openrouter", "deepseek/deepseek-v4-flash", "standard", TEXT, 0.10, 0.30, 131072),  # estimate
    ModelSpec("openrouter", "google/gemini-2.5-flash-preview", "standard", TEXT_VISION, 0.0, 0.0, 1_048_576),
)


# ── Ollama (free-text models; tier inferred from name) ───────────────────────

_OLLAMA_STRONG = re.compile(r"405b|70b|qwen.?3|qwen3|deepseek.?r1|llama.?3\.1.?405", re.I)
_OLLAMA_FAST = re.compile(r"\b(0\.5b|1b|2b|3b|4b|8b|nano|tiny|small|phi|gemma.?2)", re.I)
_OLLAMA_VISION = re.compile(r"vision|vl|medgemma|llava|qwen.?vl", re.I)


def ollama_model_spec(model_id: str) -> ModelSpec:
    """Infer a :class:`ModelSpec` for a free-text Ollama model name.

    Ollama is always free (``$0``); tier is guessed from the name (large/new =
    ``standard``/``strong``, small = ``fast``). Multimodal names are marked
    vision-capable so they can serve image extraction.
    """
    if _OLLAMA_STRONG.search(model_id):
        tier = "strong"
    elif _OLLAMA_FAST.search(model_id):
        tier = "fast"
    else:
        tier = "standard"  # safe default — local is free, so over-rating costs nothing
    modalities = TEXT_VISION if _OLLAMA_VISION.search(model_id) else TEXT
    return ModelSpec("ollama", model_id, tier, modalities, 0.0, 0.0, 0)


def spec_for(provider: str, model: str) -> ModelSpec | None:
    """The catalog spec for a cloud (provider, model), else ``None``."""
    for spec in MODEL_CATALOG:
        if spec.provider == provider and spec.model == model:
            return spec
    return None
