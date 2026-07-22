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

    async def fake_race(_prompt: str, _providers):
        call_log.append("cloud")
        return "cloud-response", "Cloud AI"

    svc._ollama_chat_stream = fake_ollama_stream  # type: ignore[method-assign]
    svc._race_providers = fake_race  # type: ignore[method-assign]
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
