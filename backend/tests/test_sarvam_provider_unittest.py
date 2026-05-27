"""Sarvam provider wiring: factory dispatch, SDK-shaped extraction, cost attribution.

Sarvam is integrated via the official ``sarvamai`` SDK (not the OpenAI SDK).
Its chat response is OpenAI-shaped, so the existing ``normalize_openai_chat``
normalizer carries the usage envelope. No live API calls — the SDK client is
replaced with an in-memory fake.
"""
from __future__ import annotations

import asyncio


def test_sarvam_in_supported_providers():
    from app.schemas.ai_settings import SUPPORTED_PROVIDERS

    assert "sarvam" in SUPPORTED_PROVIDERS


def test_factory_returns_sarvam_provider():
    from app.services.evaluators.llm_base import SarvamProvider, create_llm_provider

    provider = create_llm_provider(
        provider="sarvam", api_key="k", model_name="sarvam-m", temperature=0.1
    )
    assert isinstance(provider, SarvamProvider)
    assert provider.model_name == "sarvam-m"


def test_classname_maps_to_sarvam_key():
    from app.services.cost_tracking.provider_map import internal_provider_from_classname

    assert internal_provider_from_classname("SarvamProvider") == "sarvam"


def test_model_family_for_sarvam():
    from app.services.cost_tracking.provider_map import model_family_for

    assert model_family_for("sarvam", "sarvam-105b") == "sarvam"
    assert model_family_for("sarvam", "sarvam-m") == "sarvam"


def test_sarvam_not_in_models_dev_allowlist():
    # Sarvam is hand-seeded; a models.dev refresh must never touch its rows.
    from app.services.cost_tracking.provider_map import ALLOWLIST, PROVIDER_MAP

    assert "sarvam" not in PROVIDER_MAP.values()
    assert "sarvam" not in ALLOWLIST


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content
        self.reasoning_content = None
        self.role = "assistant"
        self.tool_calls = None


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)
        self.finish_reason = "stop"
        self.index = 0


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7
    total_tokens = 18
    prompt_tokens_details = None
    completion_tokens_details = None


class _FakeResponse:
    id = "chatcmpl-fake"
    object = "chat.completion"

    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _FakeChat:
    def __init__(self, content: str):
        self._content = content
        self.last_kwargs: dict | None = None

    def completions(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResponse(self._content)


class _FakeClient:
    def __init__(self, content: str):
        self.chat = _FakeChat(content)


def _build_provider(content: str = "नमस्ते"):
    from app.services.evaluators.llm_base import SarvamProvider

    provider = SarvamProvider(api_key="k", model_name="sarvam-m", temperature=0.2)
    provider.client = _FakeClient(content)
    return provider


def test_generate_extracts_content_tokens_and_cost_metadata():
    provider = _build_provider("नमस्ते")

    text = asyncio.run(provider.generate("Say hi in Hindi"))

    assert text == "नमस्ते"
    assert provider._last_tokens_in == 11
    assert provider._last_tokens_out == 7
    assert provider._last_metadata is not None
    # Cost attribution must tag the generation as 'sarvam', not 'openai'.
    assert provider._last_metadata["provider"] == "sarvam"
    assert provider._last_metadata["api_surface"] == "chat_completions"
    # SDK is called with the model + the OpenAI-style messages list.
    sent = provider.client.chat.last_kwargs
    assert sent["model"] == "sarvam-m"
    assert sent["messages"][-1]["content"] == "Say hi in Hindi"
    # Sarvam has no response_format param — it must never be forwarded.
    assert "response_format" not in sent


def test_generate_passes_system_prompt():
    provider = _build_provider("ok")
    asyncio.run(provider.generate("hello", system_prompt="You are terse."))
    msgs = provider.client.chat.last_kwargs["messages"]
    assert msgs[0] == {"role": "system", "content": "You are terse."}


def test_generate_json_parses_fenced_json_without_response_format():
    provider = _build_provider('```json\n{"ok": true}\n```')
    data = asyncio.run(provider.generate_json("give json", json_schema={"type": "object"}))
    assert data == {"ok": True}
    # Structured output is prompt-driven; Sarvam has no response_format.
    assert "response_format" not in provider.client.chat.last_kwargs
