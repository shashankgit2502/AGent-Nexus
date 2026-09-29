"""EmbeddingsResolver tests (ARCH §9.5 / §27.6).

The embedding mirror of the chat resolver: catalog (model_type='embedding') +
connection → a real ``Embeddings`` via ``init_embeddings``. We assert the happy
path (incl. the no-api-key Ollama branch), caching, and the two guard rails
(NotAnEmbeddingModel, ConnectionDisabled). ``init_embeddings`` constructs the
provider client lazily (no network at construction), so a dummy key is enough.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from app.core.secrets import InMemorySecretResolver
from app.models_layer.catalog import CatalogModel, InMemoryCatalogRepository
from app.models_layer.connections import InMemoryConnectionRepository, LLMConnection
from app.models_layer.embeddings import EmbeddingsResolver, _AsymmetricAwareEmbeddings
from app.models_layer.errors import ConnectionDisabled, NotAnEmbeddingModel


def _setup(
    *, model_type: str = "embedding", provider: str = "openai", enabled: bool = True
) -> tuple[EmbeddingsResolver, CatalogModel]:
    conn = LLMConnection(
        id=uuid4(),
        display_name="emb-conn",
        provider=provider,  # type: ignore[arg-type]
        base_url="http://localhost:11434" if provider == "ollama" else None,
        api_key_ref=None if provider == "ollama" else "env:KEY",
        enabled=enabled,
    )
    model = CatalogModel(
        id=uuid4(),
        provider_connection_id=conn.id,
        display_name="embed-model",
        model_identifier="nomic-embed-text" if provider == "ollama" else "text-embedding-3-small",
        model_type=model_type,  # type: ignore[arg-type]
    )
    resolver = EmbeddingsResolver(
        connections=InMemoryConnectionRepository([conn]),
        catalog=InMemoryCatalogRepository([model]),
        secrets=InMemorySecretResolver({"env:KEY": "sk-test"}),
    )
    return resolver, model


def test_resolves_openai_embeddings_and_caches() -> None:
    resolver, model = _setup(provider="openai")
    emb = resolver.resolve(model.id)
    assert isinstance(emb, Embeddings)
    # §27.4: cached by model_id — same instance on the second call.
    assert resolver.resolve(model.id) is emb


def test_resolves_ollama_embeddings_without_api_key() -> None:
    """The _NO_API_KEY + base_url branch must build without a secret (local Ollama)."""
    resolver, model = _setup(provider="ollama")
    assert isinstance(resolver.resolve(model.id), Embeddings)


def test_rejects_non_embedding_model() -> None:
    resolver, model = _setup(model_type="chat")
    with pytest.raises(NotAnEmbeddingModel):
        resolver.resolve(model.id)


def test_rejects_disabled_connection() -> None:
    resolver, model = _setup(enabled=False)
    with pytest.raises(ConnectionDisabled):
        resolver.resolve(model.id)


def test_invalidate_clears_cache() -> None:
    resolver, model = _setup()
    first = resolver.resolve(model.id)
    resolver.invalidate()
    assert resolver.resolve(model.id) is not first


def test_openai_compatible_sends_raw_text_not_tokens() -> None:
    """An ``openai_compatible`` connection is the OpenAI client at a third-party base_url
    (NVIDIA, vLLM, …). It must disable client-side tiktoken tokenization, else it POSTs
    integer token arrays that those servers reject ('list' object has no attribute
    'strip' → 500). The resolved object is the asymmetric-aware adapter; its underlying
    plain client carries the flag."""
    resolver, model = _setup(provider="openai_compatible")
    emb = resolver.resolve(model.id)
    assert isinstance(emb, _AsymmetricAwareEmbeddings)
    plain = emb._plain
    assert isinstance(plain, OpenAIEmbeddings)
    assert plain.check_embedding_ctx_length is False


def test_real_openai_keeps_ctx_length_check() -> None:
    """Positive control: the override is scoped to ``openai_compatible`` — genuine OpenAI
    keeps the default (its API accepts token arrays; the check preserves length safety)."""
    resolver, model = _setup(provider="openai")
    emb = resolver.resolve(model.id)
    assert isinstance(emb, _AsymmetricAwareEmbeddings)
    plain = emb._plain
    assert isinstance(plain, OpenAIEmbeddings)
    assert plain.check_embedding_ctx_length is True


def test_ollama_is_not_wrapped_in_asymmetric_adapter() -> None:
    """Non-OpenAI-client providers (Ollama) build directly — they never face the
    ``input_type`` requirement, so they are not wrapped."""
    resolver, model = _setup(provider="ollama")
    assert not isinstance(resolver.resolve(model.id), _AsymmetricAwareEmbeddings)


# ── Asymmetric-model (input_type) negotiation — provider-agnostic adapter ───────
class _FakeEmbeddings(Embeddings):
    """Mimics an OpenAI-compatible endpoint: without ``input_type`` it raises the
    asymmetric-model 400; with one it returns deterministic vectors."""

    def __init__(self, input_type: str | None, *, asymmetric: bool) -> None:
        self.input_type = input_type
        self._asymmetric = asymmetric

    def _guard(self) -> None:
        if self._asymmetric and self.input_type is None:
            raise RuntimeError(
                "Error code: 400 - {'error': \"'input_type' parameter is required "
                'for asymmetric models"}'
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._guard()
        return [[float(len(t))] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self._guard()
        return [float(len(text))]


def _recording_make(
    *, asymmetric: bool
) -> tuple[Callable[[str | None], Embeddings], list[str | None]]:
    seen: list[str | None] = []

    def make(input_type: str | None) -> Embeddings:
        seen.append(input_type)
        return _FakeEmbeddings(input_type, asymmetric=asymmetric)

    return make, seen


def test_adapter_negotiates_input_type_for_asymmetric_documents() -> None:
    make, seen = _recording_make(asymmetric=True)
    adapter = _AsymmetricAwareEmbeddings(make)

    # First call: plain (input_type=None) 400s → adapter retries as 'passage'.
    assert adapter.embed_documents(["abcd"]) == [[4.0]]
    assert seen == [None, "passage"]  # built plain, then the passage variant

    # Latched: a second batch goes straight to the passage variant (no re-probe).
    assert adapter.embed_documents(["xy"]) == [[2.0]]
    assert seen == [None, "passage"]


def test_adapter_uses_query_input_type_for_search() -> None:
    make, seen = _recording_make(asymmetric=True)
    adapter = _AsymmetricAwareEmbeddings(make)
    assert adapter.embed_query("hello") == [5.0]
    assert seen == [None, "query"]  # queries embed with 'query', not 'passage'


def test_adapter_is_passthrough_for_symmetric_models() -> None:
    make, seen = _recording_make(asymmetric=False)
    adapter = _AsymmetricAwareEmbeddings(make)
    assert adapter.embed_documents(["abc"]) == [[3.0]]
    assert seen == [None]  # plain client only — no input_type variant ever built


def test_adapter_reraises_non_input_type_errors() -> None:
    def make(input_type: str | None) -> Embeddings:
        class _Boom(Embeddings):
            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("Error code: 401 - invalid api key")

            def embed_query(self, text: str) -> list[float]:
                raise RuntimeError("Error code: 401 - invalid api key")

        return _Boom()

    adapter = _AsymmetricAwareEmbeddings(make)
    with pytest.raises(RuntimeError, match="invalid api key"):
        adapter.embed_documents(["x"])
