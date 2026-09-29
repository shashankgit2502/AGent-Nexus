"""Tests for ``ModelResolver`` (ARCH §9.1/§27.4) — the Step 3 acceptance gate.

Acceptance (BUILD_PLAYBOOK Step 3): ``resolve_model()`` returns a working
``init_chat_model`` for **OpenAI, Ollama, and OpenRouter**. We assert the
resolver returns the correct concrete chat-model class with the connection's
``base_url``/key and the profile's translated params applied — without any
network call (clients construct lazily).
"""

from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_openrouter import ChatOpenRouter

from app.core.secrets import InMemorySecretResolver
from app.models_layer.catalog import CatalogModel, InMemoryCatalogRepository
from app.models_layer.connections import InMemoryConnectionRepository, LLMConnection
from app.models_layer.errors import (
    ConnectionDisabled,
    ModelNotToolCapable,
    NoModelConfigured,
)
from app.models_layer.profiles import InferenceProfile, InMemoryProfileRepository
from app.models_layer.resolver import AgentModelRef, ModelResolver, resolve_model
from app.models_layer.translate_params import Provider


def _ids(n: int) -> list[UUID]:
    return [uuid.uuid4() for _ in range(n)]


def _make_resolver(
    *,
    provider: Provider,
    base_url: str | None,
    api_key_ref: str | None,
    supports_tools: bool = True,
    model_identifier: str = "test-model",
    enabled: bool = True,
    reasoning_level: str | None = None,
    deployment_name: str | None = None,
) -> tuple[ModelResolver, AgentModelRef]:
    conn_id, model_id, profile_id = _ids(3)
    connections = InMemoryConnectionRepository(
        [
            LLMConnection(
                id=conn_id,
                display_name=f"{provider} conn",
                provider=provider,
                base_url=base_url,
                api_key_ref=api_key_ref,
                api_version="2024-02-01" if provider == "azure_openai" else None,
                enabled=enabled,
            )
        ]
    )
    catalog = InMemoryCatalogRepository(
        [
            CatalogModel(
                id=model_id,
                provider_connection_id=conn_id,
                display_name=model_identifier,
                model_identifier=model_identifier,
                supports_tools=supports_tools,
                deployment_name=deployment_name,
            )
        ]
    )
    profiles = InMemoryProfileRepository(
        [
            InferenceProfile(
                id=profile_id,
                name="default",
                default_model_id=model_id,
                temperature=0.4,
                max_tokens=512,
                reasoning_level=reasoning_level,  # type: ignore[arg-type]
            )
        ]
    )
    secrets = InMemorySecretResolver({"secret://key": "resolved-key"} if api_key_ref else {})
    resolver = ModelResolver(
        connections=connections, catalog=catalog, profiles=profiles, secrets=secrets
    )
    return resolver, AgentModelRef(profile_id=profile_id)


# ── Acceptance: OpenAI / Ollama / OpenRouter resolve to working clients ───────


def test_resolve_openai() -> None:
    resolver, ref = _make_resolver(
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key_ref="secret://key",
        model_identifier="gpt-4o-mini",
    )
    model = resolve_model(resolver, ref)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "gpt-4o-mini"
    assert model.openai_api_base == "https://api.openai.com/v1"
    assert model.openai_api_key.get_secret_value() == "resolved-key"
    assert model.temperature == 0.4


def test_resolve_ollama_without_api_key() -> None:
    """Ollama takes no api_key; resolver must not pass one (ChatOllama rejects it)."""
    resolver, ref = _make_resolver(
        provider="ollama",
        base_url="http://localhost:11434",
        api_key_ref=None,
        model_identifier="llama3",
    )
    model = resolve_model(resolver, ref)
    assert isinstance(model, ChatOllama)
    assert model.model == "llama3"
    assert model.base_url == "http://localhost:11434"
    assert model.temperature == 0.4


def test_resolve_openrouter() -> None:
    resolver, ref = _make_resolver(
        provider="openrouter",
        base_url=None,
        api_key_ref="secret://key",
        model_identifier="anthropic/claude-3.5-sonnet",
    )
    model = resolve_model(resolver, ref)
    assert isinstance(model, ChatOpenRouter)
    assert model.model_name == "anthropic/claude-3.5-sonnet"
    assert model.openrouter_api_key.get_secret_value() == "resolved-key"
    assert model.max_tokens == 512


def test_openai_compatible_maps_to_openai_client_with_base_url() -> None:
    """openai_compatible has no native init_chat_model branch → maps to openai."""
    resolver, ref = _make_resolver(
        provider="openai_compatible",
        base_url="https://llm.internal.example/v1",
        api_key_ref="secret://key",
        model_identifier="local-model",
    )
    model = resolve_model(resolver, ref)
    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_base == "https://llm.internal.example/v1"
    # The per-chunk stream watchdog is turned OFF: it can't tell a reasoning model
    # "thinking" from a hung peer, so it false-trips and aborts streamed turns. The
    # provider-agnostic per-turn timeout is the resilience bound instead (R3/R4).
    assert model.stream_chunk_timeout is None


def test_resolve_anthropic_reasoning_applies_thinking() -> None:
    resolver, ref = _make_resolver(
        provider="anthropic",
        base_url=None,
        api_key_ref="secret://key",
        model_identifier="claude-sonnet-4-6",
        reasoning_level="high",
    )
    model = resolve_model(resolver, ref)
    assert isinstance(model, ChatAnthropic)
    assert model.thinking == {"type": "enabled", "budget_tokens": 8192}
    # The OpenAI-only stream watchdog kwarg must NOT be passed to non-OpenAI clients.
    assert not hasattr(model, "stream_chunk_timeout")


# ── The §9.3 supports_tools hard gate ─────────────────────────────────────────


def test_require_tools_rejects_non_tool_model() -> None:
    resolver, ref = _make_resolver(
        provider="openai",
        base_url=None,
        api_key_ref="secret://key",
        supports_tools=False,
    )
    with pytest.raises(ModelNotToolCapable):
        resolve_model(resolver, ref, require_tools=True)


def test_synthesizer_path_allows_non_tool_model() -> None:
    """require_tools=False (Synthesizer / cheap framing model) bypasses the gate."""
    resolver, ref = _make_resolver(
        provider="openai",
        base_url=None,
        api_key_ref="secret://key",
        supports_tools=False,
    )
    model = resolve_model(resolver, ref, require_tools=False)
    assert isinstance(model, ChatOpenAI)


# ── Q1 override, disabled connection, missing model, caching ──────────────────


def test_override_model_id_wins_over_profile_default() -> None:
    conn_id, default_id, override_id, profile_id = _ids(4)
    connections = InMemoryConnectionRepository(
        [LLMConnection(id=conn_id, display_name="c", provider="openai", api_key_ref="secret://key")]
    )
    catalog = InMemoryCatalogRepository(
        [
            CatalogModel(
                id=default_id,
                provider_connection_id=conn_id,
                display_name="default",
                model_identifier="default-model",
                supports_tools=True,
            ),
            CatalogModel(
                id=override_id,
                provider_connection_id=conn_id,
                display_name="override",
                model_identifier="override-model",
                supports_tools=True,
            ),
        ]
    )
    profiles = InMemoryProfileRepository(
        [InferenceProfile(id=profile_id, name="p", default_model_id=default_id)]
    )
    resolver = ModelResolver(
        connections=connections,
        catalog=catalog,
        profiles=profiles,
        secrets=InMemorySecretResolver({"secret://key": "resolved-key"}),
    )
    ref = AgentModelRef(profile_id=profile_id, override_model_id=override_id)
    model = resolver.resolve(ref)
    assert model.model_name == "override-model"


def test_no_model_configured_raises() -> None:
    profile_id = uuid.uuid4()
    profiles = InMemoryProfileRepository(
        [InferenceProfile(id=profile_id, name="p", default_model_id=None)]
    )
    resolver = ModelResolver(
        connections=InMemoryConnectionRepository(),
        catalog=InMemoryCatalogRepository(),
        profiles=profiles,
        secrets=InMemorySecretResolver(),
    )
    with pytest.raises(NoModelConfigured):
        resolver.resolve(AgentModelRef(profile_id=profile_id))


def test_disabled_connection_raises() -> None:
    resolver, ref = _make_resolver(
        provider="openai", base_url=None, api_key_ref=None, enabled=False
    )
    with pytest.raises(ConnectionDisabled):
        resolve_model(resolver, ref)


def test_resolution_is_cached_and_invalidatable() -> None:
    resolver, ref = _make_resolver(provider="openai", base_url=None, api_key_ref="secret://key")
    first = resolver.resolve(ref)
    assert resolver.resolve(ref) is first  # cache hit returns same instance
    resolver.invalidate()
    assert resolver.resolve(ref) is not first  # rebuilt after invalidation
