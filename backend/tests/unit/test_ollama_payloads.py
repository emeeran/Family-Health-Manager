"""Unit tests for Ollama payload tuning.

Asserts the CPU-path speed fixes are actually present in every outgoing
payload: ``num_thread`` pinning (was omitted from all 5 payloads, so Ollama
underused SMT), ``keep_alive`` on the two payloads that previously omitted it
(``chat_stream`` + ``ocr`` — causing ~9s cold-load stalls), and the vision
extraction ``num_predict`` cap (4096 → 1024; structured JSON is ~200–500
tokens). No network — the shared Ollama client and provider URL are faked.
"""

import json

import pytest

from app.services.ai.providers import ollama


class _FakeResponse:
    """httpx response stand-in supporting both ``json()`` and ``aiter_lines()``."""

    def __init__(self, payload, with_lines=False):
        self._payload = payload
        self._with_lines = with_lines

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

    def aiter_lines(self):
        async def _gen():
            if self._with_lines:
                yield json.dumps(self._payload)

        return _gen()


class _FakeClient:
    """Captures every POST/STREAM payload so tests can assert on options."""

    def __init__(self):
        self.posted: list[dict] = []

    async def post(self, url, json=None, timeout=None):
        self.posted.append(json)
        return _FakeResponse({"message": {"content": "ok"}})

    def stream(self, method, url, json=None, timeout=None):
        self.posted.append(json)
        payload = {"message": {"content": "ok"}, "done": True}

        class _CM:
            async def __aenter__(self):
                return _FakeResponse(payload, with_lines=True)

            async def __aexit__(self, *exc):
                return False

        return _CM()


def _async_return(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn


@pytest.fixture
def fake_ollama(monkeypatch):
    """Patch the shared client + provider URL so Ollama calls run fully offline."""
    client = _FakeClient()
    monkeypatch.setattr(ollama, "get_ollama_client", _async_return(client))
    monkeypatch.setattr(ollama, "resolve_provider_value", _async_return("http://ollama:11434"))
    # Local vision is opt-in (disabled by default); enable it here so the
    # vision/ocr payloads are actually exercised.
    monkeypatch.setattr(ollama.settings, "OLLAMA_VISION_MODEL", "llama3.2-vision")
    return client


async def test_num_thread_pinned_in_every_payload(fake_ollama):
    """OLLAMA_NUM_THREAD (default = logical core count) reaches every call type."""
    await ollama.call_ollama_text("hi")
    await ollama.call_ollama_vision("b64", "image/png", "prompt")
    await ollama.call_ollama_ocr("b64", "image/png")
    async for _ in ollama.ollama_chat_stream("model", "hi"):
        pass

    assert fake_ollama.posted, "no payloads were captured"
    expected = ollama.settings.OLLAMA_NUM_THREAD
    for payload in fake_ollama.posted:
        assert payload["options"]["num_thread"] == expected


async def test_zero_num_thread_omits_it(monkeypatch, fake_ollama):
    """OLLAMA_NUM_THREAD=0 defers to Ollama's auto-selection (no key sent)."""
    monkeypatch.setattr(ollama.settings, "OLLAMA_NUM_THREAD", 0)
    await ollama.call_ollama_text("hi")
    assert "num_thread" not in fake_ollama.posted[-1]["options"]


async def test_keep_alive_on_previously_missing_payloads(fake_ollama):
    """chat_stream + ocr previously omitted keep_alive (cold-load stalls)."""
    await ollama.call_ollama_ocr("b64", "image/png")
    assert fake_ollama.posted[-1]["keep_alive"] == ollama.settings.OLLAMA_KEEP_ALIVE

    async for _ in ollama.ollama_chat_stream("model", "hi"):
        pass
    assert fake_ollama.posted[-1]["keep_alive"] == ollama.settings.OLLAMA_KEEP_ALIVE


async def test_vision_extraction_num_predict_capped(fake_ollama):
    """Vision extraction returns short JSON — num_predict was 4096, now 1024."""
    await ollama.call_ollama_vision("b64", "image/png", "prompt")
    assert fake_ollama.posted[-1]["options"]["num_predict"] == 1024


async def test_structured_text_suppresses_thinking(fake_ollama):
    """fmt='json' (extraction) appends /no_think + sets think=false for speed."""
    await ollama.call_ollama_text("Extract the fields", fmt="json")
    payload = fake_ollama.posted[-1]
    assert payload["format"] == "json"
    assert payload["think"] is False
    assert payload["messages"][0]["content"].endswith("/no_think")


async def test_plain_text_leaves_thinking_alone(fake_ollama):
    """Non-structured text (general chat) must not touch thinking."""
    await ollama.call_ollama_text("hi")
    payload = fake_ollama.posted[-1]
    assert "think" not in payload
    assert "format" not in payload
    assert not payload["messages"][0]["content"].endswith("/no_think")


async def test_vision_without_model_is_skipped(monkeypatch, fake_ollama):
    """No OLLAMA_VISION_MODEL → vision call returns None without hitting the API."""
    monkeypatch.setattr(ollama.settings, "OLLAMA_VISION_MODEL", "")
    assert await ollama.call_ollama_vision("b64", "image/png", "prompt") is None
    assert await ollama.call_ollama_ocr("b64", "image/png") is None
    assert fake_ollama.posted == []  # nothing sent


async def test_vision_multi_sends_all_images_in_one_call(fake_ollama):
    """Multi-image vision packs every page into one ``images`` list (B2)."""
    await ollama.call_ollama_vision_multi(
        ["imgA", "imgB", "imgC"], "image/png", "prompt", fmt="json"
    )
    payload = fake_ollama.posted[-1]
    assert payload["messages"][0]["images"] == ["imgA", "imgB", "imgC"]
    assert payload["format"] == "json"  # grammar-constrained like single vision
    assert payload["options"]["num_predict"] == 1024


async def test_vision_multi_empty_list_returns_none(fake_ollama):
    assert await ollama.call_ollama_vision_multi([], "image/png", "prompt") is None
    assert fake_ollama.posted == []
