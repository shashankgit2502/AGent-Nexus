"""Tests for provider model discovery / validation probe (ARCH §27.2/§27.3).

Uses ``httpx.MockTransport`` so URL derivation, auth headers, response parsing,
SSRF guarding, and error handling are exercised without any network access.
"""

from __future__ import annotations

import httpx
import pytest

from app.models_layer.discovery import classify_model_type, discover_models

pytestmark = pytest.mark.asyncio


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_classify_model_type_flags_embedding_ids() -> None:
    """Best-effort id heuristic (Approach B): 'embed' in the id → embedding, else chat.

    Providers' ``/models`` rarely tag chat vs embedding, so discovery classifies by
    the id and the user can always correct it via PATCH /providers/catalog/{id}.
    """
    for embed_id in ("nemotron:embed", "text-embedding-3-large", "BAAI/bge-embedding"):
        assert classify_model_type(embed_id) == "embedding"
    for chat_id in ("gpt-4o", "claude-opus-4-8", "mistralai/mistral-small"):
        assert classify_model_type(chat_id) == "chat"


async def test_discovery_classifies_embedding_models_by_id() -> None:
    """A discovered embedding-looking id carries ``model_type='embedding'`` (no hardcode)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"id": "text-embedding-3-small"}, {"id": "gpt-4o"}]}
        )

    async with _client(handler) as client:
        result = await discover_models(
            provider="openai", base_url=None, api_key="sk", client=client
        )

    by_id = {m.id: m for m in result.models}
    assert by_id["text-embedding-3-small"].model_type == "embedding"
    assert by_id["gpt-4o"].model_type == "chat"


async def test_openrouter_lists_models_and_normalizes_chat_completions_url() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": [{"id": "openai/gpt-4o"}, {"id": "x/y"}]})

    # User pasted the chat/completions endpoint as base_url (the Bug 5 repro).
    async with _client(handler) as client:
        result = await discover_models(
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1/chat/completions",
            api_key="sk-or-v1-abc",
            client=client,
        )

    assert result.ok is True
    assert result.model_ids == ["openai/gpt-4o", "x/y"]
    # The trailing /chat/completions is stripped back to /v1/models.
    assert seen["url"] == "https://openrouter.ai/api/v1/models"
    assert seen["auth"] == "Bearer sk-or-v1-abc"


async def test_openrouter_parses_capabilities_from_supported_parameters() -> None:
    """Regression (root cause: every catalog model was supports_tools=false).

    Discovery previously read only ids, so the §9.3 tool gate rejected every
    model and all runs fell back to the stub. It must now read the capability
    fields OpenRouter ships inline.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "mistralai/mistral-small",
                        "supported_parameters": ["tools", "temperature", "reasoning"],
                        "architecture": {"input_modalities": ["text", "image"]},
                        "context_length": 128000,
                    },
                    {"id": "some/embedding-only", "supported_parameters": ["temperature"]},
                ]
            },
        )

    async with _client(handler) as client:
        result = await discover_models(
            provider="openrouter", base_url=None, api_key="sk-or-v1-x", client=client
        )

    assert result.ok is True
    tool = next(m for m in result.models if m.id == "mistralai/mistral-small")
    assert tool.supports_tools is True
    assert tool.supports_vision is True
    assert tool.supports_reasoning is True
    assert tool.context_window == 128000
    plain = next(m for m in result.models if m.id == "some/embedding-only")
    assert plain.supports_tools is False
    assert plain.supports_vision is False
    # Back-compat id list still works for id-only callers.
    assert result.model_ids == ["mistralai/mistral-small", "some/embedding-only"]


async def test_ollama_uses_tags_endpoint_and_parses_names() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://localhost:11434/api/tags"
        return httpx.Response(200, json={"models": [{"name": "llama3"}, {"name": "qwen"}]})

    async with _client(handler) as client:
        result = await discover_models(
            provider="ollama",
            base_url="http://localhost:11434",
            api_key=None,
            allow_private=True,  # local host requires the private allowance
            client=client,
        )

    assert result.ok is True
    assert result.model_ids == ["llama3", "qwen"]


async def test_anthropic_sends_version_and_api_key_headers() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["version"] = request.headers.get("anthropic-version")
        seen["key"] = request.headers.get("x-api-key")
        return httpx.Response(200, json={"data": [{"id": "claude-sonnet-4-6"}]})

    async with _client(handler) as client:
        result = await discover_models(
            provider="anthropic", base_url=None, api_key="sk-ant", client=client
        )

    assert result.ok is True
    assert seen["version"]  # a default version is always sent
    assert seen["key"] == "sk-ant"


async def test_http_error_is_reported_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    async with _client(handler) as client:
        result = await discover_models(
            provider="openai", base_url=None, api_key="bad", client=client
        )

    assert result.ok is False
    assert "401" in result.detail or "Unauthorized" in result.detail


async def test_ssrf_blocked_base_url_fails_closed() -> None:
    # A private host without allow_private must be rejected before any request.
    result = await discover_models(
        provider="openai_compatible",
        base_url="http://169.254.169.254/latest",  # cloud metadata endpoint
        api_key="k",
    )
    assert result.ok is False
    assert "SSRFBlocked" in result.detail
