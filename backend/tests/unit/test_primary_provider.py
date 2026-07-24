"""Tests for the primary-provider (Cloud vs Local) configuration."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.ai_provider_config import (
    AIProviderConfig,
    ProviderConfigItem,
    default_provider_config,
)
from app.services.ai import AIService


def _cfg(primary: str) -> AIProviderConfig:
    return AIProviderConfig(
        providers=[
            ProviderConfigItem(id="ollama", enabled=True, model="medgemma"),
            ProviderConfigItem(id="openrouter", enabled=True, model="x"),
            ProviderConfigItem(id="gemini", enabled=True, model="gemini-2.5-flash"),
            ProviderConfigItem(id="openai", enabled=True, model="gpt"),
        ],
        primary_provider=primary,  # type: ignore[arg-type]
    )


def test_default_primary_provider_is_auto():
    """New configs default to 'auto' (cloud-first when a key exists, else local).

    See C1: a freshly-keyed household becomes cloud-first (30-60x faster) with
    no manual Settings change; an Ollama-only box stays local-first.
    """
    assert default_provider_config().primary_provider == "auto"


def test_primary_provider_accepts_cloud():
    cfg = AIProviderConfig(providers=[], primary_provider="cloud")  # type: ignore[arg-type]
    assert cfg.primary_provider == "cloud"


def test_ordered_providers_local_first():
    ordered = AIService._ordered_providers(_cfg("local"))
    assert [p.id for p in ordered] == ["ollama", "openrouter", "gemini", "openai"]


def test_ordered_providers_cloud_first():
    ordered = AIService._ordered_providers(_cfg("cloud"))
    assert [p.id for p in ordered] == ["openrouter", "gemini", "openai", "ollama"]


def test_ordered_providers_preserves_intra_group_order():
    # gemini before openrouter in the array -> stays that way within the cloud group.
    cfg = AIProviderConfig(
        providers=[
            ProviderConfigItem(id="gemini", enabled=True, model=""),
            ProviderConfigItem(id="ollama", enabled=True, model=""),
            ProviderConfigItem(id="openrouter", enabled=True, model=""),
        ],
        primary_provider="cloud",  # type: ignore[arg-type]
    )
    assert [p.id for p in AIService._ordered_providers(cfg)] == [
        "gemini",
        "openrouter",
        "ollama",
    ]


class _FakeDB:
    """Minimal async-session stub: chat_stream only add()s + flush()es, plus
    one history query that we return empty for."""

    def add(self, _obj: object) -> None:
        pass

    async def flush(self) -> None:
        return None

    async def execute(self, *_a: object, **_k: object):
        class _Result:
            def scalars(self_inner):
                class _Scalars:
                    def all(self_inner2):
                        return []

                return _Scalars()

        return _Result()


class _FakeMessage:
    """Stand-in for Message: a real flush populates id/created_at, but our
    fake DB doesn't, so set them on construction."""

    def __init__(self, **kwargs: object) -> None:
        self.id = uuid4()
        self.created_at = datetime.now(timezone.utc)
        self.__dict__.update(kwargs)


class _FakeInsight:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


def _stream_chat_spy(monkeypatch, primary: str) -> tuple[AIService, list[str]]:
    """Build an AIService whose local/cloud streaming paths record call order."""
    import app.services.ai as ai_mod

    monkeypatch.setattr(ai_mod, "Message", _FakeMessage)
    monkeypatch.setattr(ai_mod, "AIInsight", _FakeInsight)

    call_log: list[str] = []
    svc = AIService(db=_FakeDB())

    async def cfg():
        return _cfg(primary)

    svc._get_provider_config = cfg  # type: ignore[method-assign]
    # Return a truthy callable for every provider id so cloud_providers populates.
    svc._get_provider_fn = lambda _pid: (lambda *a, **k: None)  # type: ignore[method-assign]

    async def fake_ollama_stream(_model: str, _prompt: str):
        call_log.append("local")
        yield "local-response"

    async def fake_cloud_seq(_prompt: str, _providers):
        call_log.append("cloud")
        return "cloud-response", "Cloud AI"

    svc._ollama_chat_stream = fake_ollama_stream  # type: ignore[method-assign]
    svc._call_cloud_sequential = fake_cloud_seq  # type: ignore[method-assign]
    return svc, call_log


@pytest.mark.asyncio
async def test_chat_stream_cloud_primary_tries_cloud_first(monkeypatch):
    """Regression: streaming chat must honor primary_provider. Previously
    chat_stream always tried Ollama first and used cloud only as a fallback,
    ignoring primary='cloud' (unlike generate_insight_stream)."""
    svc, call_log = _stream_chat_spy(monkeypatch, "cloud")
    events = [
        e async for e in svc.chat_stream(uuid4(), "hello", member_id=None, household_id=None)
    ]
    assert call_log == ["cloud"]
    assert any('"stage": "complete"' in e for e in events)


@pytest.mark.asyncio
async def test_chat_stream_local_primary_tries_local_first(monkeypatch):
    svc, call_log = _stream_chat_spy(monkeypatch, "local")
    events = [
        e async for e in svc.chat_stream(uuid4(), "hello", member_id=None, household_id=None)
    ]
    assert call_log == ["local"]
    assert any('"stage": "complete"' in e for e in events)


# ---- _call_cloud_sequential: strict Groq → Gemini → … failover (no race) ----


@pytest.mark.asyncio
async def test_call_cloud_sequential_short_circuits_on_first_success():
    """First non-empty cloud result wins; later providers are never called."""
    svc = AIService(db=_FakeDB())
    calls: list[str] = []

    async def ok_groq(_p, *, model=""):
        calls.append("groq")
        return "groq-answer"

    async def never_gemini(_p, *, model=""):
        calls.append("gemini")
        return "should-not-happen"

    cloud = [(ok_groq, "Groq (g)", "g"), (never_gemini, "Google Gemini (gm)", "gm")]
    result = await svc._call_cloud_sequential("prompt", cloud)
    assert result == ("groq-answer", "Groq (g)")
    assert calls == ["groq"]


@pytest.mark.asyncio
async def test_call_cloud_sequential_falls_through_on_failure():
    """A failing/empty provider is skipped and the next is tried in order."""
    svc = AIService(db=_FakeDB())
    calls: list[str] = []

    async def fails_groq(_p, *, model=""):
        calls.append("groq")
        raise RuntimeError("boom")

    async def empty_gemini(_p, *, model=""):
        calls.append("gemini")
        return ""

    async def ok_openai(_p, *, model=""):
        calls.append("openai")
        return "openai-answer"

    cloud = [
        (fails_groq, "Groq (g)", "g"),
        (empty_gemini, "Google Gemini (gm)", "gm"),
        (ok_openai, "OpenAI (o)", "o"),
    ]
    result = await svc._call_cloud_sequential("prompt", cloud)
    assert result == ("openai-answer", "OpenAI (o)")
    assert calls == ["groq", "gemini", "openai"]


@pytest.mark.asyncio
async def test_call_cloud_sequential_returns_none_when_all_fail():
    svc = AIService(db=_FakeDB())

    async def fails(_p, *, model=""):
        raise RuntimeError("boom")

    async def empty(_p, *, model=""):
        return ""

    cloud = [(fails, "Groq (g)", "g"), (empty, "Google Gemini (gm)", "gm")]
    assert await svc._call_cloud_sequential("prompt", cloud) is None


@pytest.mark.asyncio
async def test_call_cloud_sequential_skips_open_circuit(monkeypatch):
    """Providers with an open circuit breaker are skipped without being called."""
    import app.services.ai.base as base

    svc = AIService(db=_FakeDB())
    calls: list[str] = []

    # Groq breaker is "open"; Gemini is available.
    monkeypatch.setattr(base, "is_provider_available", lambda label: not label.startswith("Groq"))

    async def skipped_groq(_p, *, model=""):
        calls.append("groq")
        return "x"

    async def ok_gemini(_p, *, model=""):
        calls.append("gemini")
        return "gemini-answer"

    cloud = [(skipped_groq, "Groq (g)", "g"), (ok_gemini, "Google Gemini (gm)", "gm")]
    result = await svc._call_cloud_sequential("prompt", cloud)
    assert result == ("gemini-answer", "Google Gemini (gm)")
    assert calls == ["gemini"]


# ---- _call_validator: cloud-preferred, different-family selection ----


def _validator_svc(
    monkeypatch, primary: str, providers: list[ProviderConfigItem]
) -> AIService:
    """AIService wired with a fixed config + fake provider fns for validator tests.

    All providers are treated as keyed (so the task router's route() considers
    every configured provider, independent of real env keys).
    """
    async def _configured(_pid: str) -> bool:
        return True

    monkeypatch.setattr("app.services.ai.task_router.is_provider_configured", _configured)

    svc = AIService(db=_FakeDB())
    cfg = AIProviderConfig(providers=providers, primary_provider=primary)  # type: ignore[arg-type]

    async def cfg_fn():
        return cfg

    svc._get_provider_config = cfg_fn  # type: ignore[method-assign]

    async def groq_fn(_p, *, model=""):
        return "from-groq"

    async def gemini_fn(_p, *, model=""):
        return "from-gemini"

    async def ollama_fn(_p, *, model=""):
        return "from-ollama"

    async def openrouter_fn(_p, *, model=""):
        return "from-openrouter"

    fns = {
        "groq": groq_fn,
        "gemini": gemini_fn,
        "ollama": ollama_fn,
        "openrouter": openrouter_fn,
    }
    svc._get_provider_fn = lambda pid: fns.get(pid)  # type: ignore[method-assign]
    return svc


@pytest.mark.asyncio
async def test_call_validator_skips_generator_family_prefers_cloud(monkeypatch):
    """Generator=Groq -> validator is a different family, cloud-preferred (Gemini)."""
    svc = _validator_svc(
        monkeypatch,
        "cloud",
        [
            ProviderConfigItem(id="groq", enabled=True, model="g1"),
            ProviderConfigItem(id="ollama", enabled=True, model="m"),
            ProviderConfigItem(id="gemini", enabled=True, model="gm"),
        ],
    )
    result = await svc._call_validator("prompt", generator_label="Groq (g1)")
    assert result is not None
    text, label = result
    assert text == "from-gemini"
    assert label.startswith("Google Gemini")


@pytest.mark.asyncio
async def test_call_validator_returns_none_for_single_provider_household(monkeypatch):
    """Only-Ollama household + Ollama generator -> no different-family validator -> None."""
    svc = _validator_svc(
        monkeypatch, "local", [ProviderConfigItem(id="ollama", enabled=True, model="m")]
    )
    assert await svc._call_validator("prompt", generator_label="Ollama m") is None


@pytest.mark.asyncio
async def test_call_validator_picks_cheapest_different_family(monkeypatch):
    """Generator=Groq; OpenRouter BEFORE Gemini in config. The router picks by
    cost, so Gemini (free tier) wins regardless of config order or the
    preference flag — config order never forces the earlier provider."""
    svc = _validator_svc(
        monkeypatch,
        "cloud",
        [
            ProviderConfigItem(id="groq", enabled=True, model="g1"),
            ProviderConfigItem(id="openrouter", enabled=True, model="or"),
            ProviderConfigItem(id="gemini", enabled=True, model="gm"),
        ],
    )
    result = await svc._call_validator("prompt", generator_label="Groq (g1)")
    assert result is not None
    text, label = result
    # Groq (generator family) excluded; Gemini is cheapest capable -> chosen.
    assert text == "from-gemini"
    assert label.startswith("Google Gemini")
