"""Embeddings resolution (ARCHITECTURE.md §9.5 / §27.6).

The mirror of :class:`~app.models_layer.resolver.ModelResolver` for the *embedding*
side of the catalog. Embedding models are first-class catalog rows
(``model_type="embedding"``) reachable through the **same** Connection layer, and
they are resolved to a real :class:`~langchain_core.embeddings.Embeddings` via
``langchain.embeddings.init_embeddings`` (R1-verified against langchain 1.3.9:
``init_embeddings(model, *, provider=None, **kwargs)``).

One resolver, two stores: the resolved ``Embeddings`` powers **both** RAG
(Knowledge, §10.5) and — when configured — semantic search in the long-term Store
(§10). The pgvector column dimension is fixed by the embedding model's output size,
so the default embedding model is a deliberate, sticky choice (§20 note 6).

Why a separate resolver from the chat one: embeddings take **no** inference params
(no temperature/reasoning), so there is no ``translate_params`` step — only the
provider/credential/base_url wiring is shared. Keeping them apart avoids forcing
the chat resolver to branch on ``model_type``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import UUID

from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings

from app.core.secrets import SecretResolver
from app.models_layer.catalog import CatalogModel, CatalogRepository
from app.models_layer.connections import ConnectionRepository, LLMConnection
from app.models_layer.errors import ConnectionDisabled, NotAnEmbeddingModel
from app.models_layer.translate_params import Provider

# Internal provider enum -> the provider string init_embeddings expects. Mirrors the
# chat resolver's map: only openai_compatible needs remapping (it *is* the OpenAI
# embeddings client pointed at a custom base_url). Providers without an embedding
# implementation (e.g. anthropic) will raise from init_embeddings — surfaced, not hidden.
_PROVIDER_MAP: dict[Provider, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "azure_openai": "azure_openai",
    "ollama": "ollama",
    "openrouter": "openrouter",
    "openai_compatible": "openai",
}

# Providers that do not take an api_key (local Ollama). Same gate as the chat resolver.
_NO_API_KEY: frozenset[str] = frozenset({"ollama"})

# Providers backed by the OpenAI embeddings client (a real or compatible OpenAI HTTP
# endpoint). Only these can surface — and accept the fix for — the ``input_type``
# requirement of asymmetric retrieval models, so only these get the adaptive adapter.
_OPENAI_CLIENT_PROVIDERS: frozenset[str] = frozenset(
    {"openai", "azure_openai", "openrouter", "openai_compatible"}
)

logger = logging.getLogger(__name__)


def _requires_input_type(exc: BaseException) -> bool:
    """True when a server rejected an embed call for lack of an ``input_type``.

    Matches the error *contract* (the standard ``input_type`` param named by NVIDIA
    NIM, Cohere, … for asymmetric models), not any vendor — so the adapter stays
    provider-agnostic. A symmetric model never produces this, so it never adapts.
    """
    return "input_type" in str(exc).lower()


class _AsymmetricAwareEmbeddings(Embeddings):
    """Make an OpenAI-compatible ``Embeddings`` work with *asymmetric* models without
    coupling to any provider or model id.

    Asymmetric retrieval models (NVIDIA ``llama-nemotron-embed``, Cohere, …) require an
    ``input_type`` that differs by direction — ``passage`` when indexing documents,
    ``query`` when embedding a search query — which a plain OpenAI request omits. Rather
    than hard-code which models need it, this adapter **negotiates with the server**: it
    tries the normal request and, only if the endpoint explicitly demands ``input_type``,
    retries with the direction-correct value and remembers the decision (so later calls
    go straight through). Symmetric models never hit the retry path and are unaffected —
    the system self-configures per endpoint, like a general document pipeline should.

    This is deliberate content negotiation, not error-swallowing (R3): a non-``input_type``
    failure is re-raised unchanged, and a successful retry returns real vectors.
    """

    # NVIDIA/OpenAI-convention values; the langchain_openai client carries them in the
    # request body via ``extra_body`` (see ``EmbeddingsResolver._build``).
    _DOC_TYPE = "passage"
    _QUERY_TYPE = "query"

    def __init__(self, make: Callable[[str | None], Embeddings]) -> None:
        self._make = make
        self._plain = make(None)
        self._typed: dict[str, Embeddings] = {}
        self._needs_input_type = False

    def _variant(self, input_type: str) -> Embeddings:
        emb = self._typed.get(input_type)
        if emb is None:
            emb = self._make(input_type)
            self._typed[input_type] = emb
        return emb

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self._needs_input_type:
            return self._variant(self._DOC_TYPE).embed_documents(texts)
        try:
            return self._plain.embed_documents(texts)
        except Exception as exc:
            if not _requires_input_type(exc):
                raise
            logger.info("embeddings: endpoint requires input_type=%s; retrying", self._DOC_TYPE)
            self._needs_input_type = True
            return self._variant(self._DOC_TYPE).embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if self._needs_input_type:
            return self._variant(self._QUERY_TYPE).embed_query(text)
        try:
            return self._plain.embed_query(text)
        except Exception as exc:
            if not _requires_input_type(exc):
                raise
            logger.info("embeddings: endpoint requires input_type=%s; retrying", self._QUERY_TYPE)
            self._needs_input_type = True
            return self._variant(self._QUERY_TYPE).embed_query(text)


class EmbeddingsResolver:
    """Resolves an embedding catalog model id to a live ``Embeddings`` (§9.5).

    Depends only on repository Protocols + a :class:`SecretResolver`, so it works
    identically over the in-memory stores (tests/dev) and the SQLAlchemy stores
    (Step 9). Resolved embeddings are cached by ``model_id`` and invalidated
    wholesale on any connection/catalog edit (Step 9 calls :meth:`invalidate`).
    """

    def __init__(
        self,
        *,
        connections: ConnectionRepository,
        catalog: CatalogRepository,
        secrets: SecretResolver,
    ) -> None:
        self._connections = connections
        self._catalog = catalog
        self._secrets = secrets
        self._cache: dict[UUID, Embeddings] = {}

    def resolve(self, model_id: UUID) -> Embeddings:
        """Build (or return a cached) embeddings client for ``model_id``.

        Raises:
            NotAnEmbeddingModel: the catalog row is not ``model_type='embedding'``.
            ConnectionDisabled: the resolved connection is disabled.
            EntityNotFound: a referenced id does not exist.
        """
        cached = self._cache.get(model_id)
        if cached is not None:
            return cached

        catalog_model = self._catalog.get(model_id)
        if catalog_model.model_type != "embedding":
            raise NotAnEmbeddingModel(catalog_model.display_name)

        connection = self._connections.get(catalog_model.provider_connection_id)
        if not connection.enabled:
            raise ConnectionDisabled(connection.display_name)

        embeddings = self._build(connection, catalog_model)
        self._cache[model_id] = embeddings
        return embeddings

    def invalidate(self) -> None:
        """Drop all cached embeddings (call on any connection/catalog edit)."""
        self._cache.clear()

    def _build(self, connection: LLMConnection, catalog_model: CatalogModel) -> Embeddings:
        provider = connection.provider
        kwargs: dict[str, object] = {}

        if provider == "azure_openai":
            if connection.base_url:
                kwargs["azure_endpoint"] = connection.base_url
            if catalog_model.deployment_name:
                kwargs["azure_deployment"] = catalog_model.deployment_name
            if connection.api_version:
                kwargs["api_version"] = connection.api_version
        elif connection.base_url:
            kwargs["base_url"] = connection.base_url

        if provider not in _NO_API_KEY:
            api_key = self._secrets.resolve(connection.api_key_ref)
            if api_key:
                kwargs["api_key"] = api_key

        # ``OpenAIEmbeddings`` defaults to ``check_embedding_ctx_length=True``, which
        # tiktoken-tokenizes client-side and sends **integer token arrays** as
        # ``input``. Only OpenAI's own endpoint (and Azure) reliably accept token
        # arrays; third-party OpenAI-compatible servers (NVIDIA, vLLM, LM Studio, …)
        # reject or 500 on them — NVIDIA's ``/embeddings`` returns a bare
        # ``Internal Server Error`` (RCA 2026-07-03) or ``'list' object has no
        # attribute 'strip'``. Disabling the ctx-length check sends raw text, the
        # langchain_openai-documented fix for custom servers (R1: verified against
        # the installed langchain_openai embeddings base).
        #
        # The gate is the **endpoint**, not the declared provider: a connection
        # registered as ``provider="openai"`` with a custom ``base_url`` (how the
        # NVIDIA connection is stored in practice) is still a third-party server, so
        # it needs raw text exactly like ``openai_compatible``. Only a default
        # (base_url-less) ``openai`` connection and ``azure_openai`` keep the token
        # array default — their servers accept it and the check preserves per-model
        # context-length safety on long inputs.
        talks_to_third_party = (
            provider in ("openai_compatible", "openrouter")
            or (provider == "openai" and bool(connection.base_url))
        )
        if talks_to_third_party:
            kwargs["check_embedding_ctx_length"] = False

        def make(input_type: str | None) -> Embeddings:
            """Build the client, optionally carrying an asymmetric-model ``input_type``.

            ``input_type`` is not a standard OpenAI field, so it rides in the request
            body via ``model_kwargs={"extra_body": ...}`` — the OpenAI SDK merges
            ``extra_body`` into the POST payload. ``None`` builds the plain client.
            """
            call_kwargs = dict(kwargs)
            if input_type is not None:
                call_kwargs["model_kwargs"] = {"extra_body": {"input_type": input_type}}
            return init_embeddings(
                catalog_model.model_identifier,
                provider=_PROVIDER_MAP[provider],
                **call_kwargs,
            )

        # Only OpenAI-client endpoints can need/accept ``input_type``; wrap them in the
        # adapter that negotiates it per request (asymmetric models work, symmetric ones
        # are untouched). Other providers (Ollama) build directly.
        if provider in _OPENAI_CLIENT_PROVIDERS:
            return _AsymmetricAwareEmbeddings(make)
        return make(None)
