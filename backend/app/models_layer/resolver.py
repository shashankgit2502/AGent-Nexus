"""The Model Resolution Layer entry point (ARCHITECTURE.md §9.1 / §27.4).

This ties the four layers together into a real LangChain chat model:

    AgentModelRef ─► InferenceProfile ─► (agent override?) ─► CatalogModel
                                                              │
                                                              ▼
                                              LLMConnection ─► secret (api_key)
                                                              │
                              translate_params(provider, profile.params)
                                                              │
                                                              ▼
                       init_chat_model(model, model_provider, base_url, api_key, **params)

Key locked behaviours implemented here:

* **Q1 — profile default + optional agent override.** ``override_model_id`` wins
  over ``profile.default_model_id``.
* **§9.3 hard gate — ``supports_tools``.** Mesh agents (``require_tools=True``)
  may only resolve tool-capable models; the Synthesizer relaxes this.
* **§27.4 caching.** Built models are cached by ``(catalog_id, profile_id,
  require_tools)`` and invalidated wholesale on any connection/catalog/profile
  edit (Step 9 will call :meth:`ModelResolver.invalidate` on writes).

R1 note — provider mapping
--------------------------
``init_chat_model`` (verified against langchain 1.3.9) natively supports the
provider strings ``openai``, ``anthropic``, ``azure_openai``, ``ollama``,
``openrouter`` — but **not** ``openai_compatible``. An OpenAI-compatible endpoint
*is* the OpenAI client pointed at a custom ``base_url``, so we map
``openai_compatible`` → ``model_provider="openai"`` and pass ``base_url``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.secrets import SecretResolver
from app.models_layer.base_url import canonical_base_url
from app.models_layer.catalog import CatalogModel, CatalogRepository
from app.models_layer.connections import ConnectionRepository, LLMConnection
from app.models_layer.errors import (
    ConnectionDisabled,
    ModelNotToolCapable,
    NoModelConfigured,
)
from app.models_layer.profiles import ProfileRepository
from app.models_layer.translate_params import NormalizedParams, Provider, translate_params

# Our internal provider enum -> the model_provider string init_chat_model expects.
# Only openai_compatible needs remapping (it has no native init_chat_model branch).
_PROVIDER_MAP: dict[Provider, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "azure_openai": "azure_openai",
    "ollama": "ollama",
    "openrouter": "openrouter",
    "openai_compatible": "openai",
}

# Providers that do not take an api_key (local Ollama). Passing one errors because
# ChatOllama has no api_key field.
_NO_API_KEY: frozenset[str] = frozenset({"ollama"})

# ``init_chat_model`` provider strings backed by the OpenAI client (``ChatOpenAI`` /
# ``AzureChatOpenAI``) — the only ones that accept ``stream_chunk_timeout``.
_OPENAI_FAMILY: frozenset[str] = frozenset({"openai", "azure_openai"})


@dataclass(frozen=True)
class AgentModelRef:
    """The minimal model-selection inputs an agent (or node) provides (§9.1).

    Mirrors the relevant columns of ``agents`` (profile_id + override_model_id)
    without coupling the resolver to the full AgentConfig that arrives in Step 4.
    """

    profile_id: UUID
    override_model_id: UUID | None = None


class ModelResolver:
    """Resolves an :class:`AgentModelRef` to a live ``BaseChatModel`` (§9.1).

    Depends only on repository Protocols + a :class:`SecretResolver`, so it works
    identically over the in-memory stores (tests/dev) and the SQLAlchemy stores
    (Step 9). Resolved models are cached per §27.4.
    """

    def __init__(
        self,
        *,
        connections: ConnectionRepository,
        catalog: CatalogRepository,
        profiles: ProfileRepository,
        secrets: SecretResolver,
    ) -> None:
        self._connections = connections
        self._catalog = catalog
        self._profiles = profiles
        self._secrets = secrets
        self._cache: dict[tuple[UUID, UUID, bool], BaseChatModel] = {}

    def resolve(self, ref: AgentModelRef, *, require_tools: bool = True) -> BaseChatModel:
        """Build (or return a cached) chat model for ``ref``.

        Args:
            ref: the agent's profile + optional model override.
            require_tools: enforce the §9.3 tool-calling gate (True for mesh
                agents; False for the Synthesizer / cheap framing models).

        Raises:
            NoModelConfigured: neither override nor profile default set a model.
            ModelNotToolCapable: ``require_tools`` and the model can't call tools.
            ConnectionDisabled: the resolved connection is disabled.
            EntityNotFound: a referenced id does not exist.
        """
        profile = self._profiles.get(ref.profile_id)
        model_id = ref.override_model_id or profile.default_model_id  # Q1
        if model_id is None:
            raise NoModelConfigured(
                f"profile {profile.name!r} has no default model and no override given"
            )

        cache_key = (model_id, ref.profile_id, require_tools)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        catalog_model = self._catalog.get(model_id)
        if require_tools and not catalog_model.supports_tools:
            raise ModelNotToolCapable(catalog_model.display_name)  # §9.3 hard gate

        connection = self._connections.get(catalog_model.provider_connection_id)
        if not connection.enabled:
            raise ConnectionDisabled(connection.display_name)

        model = self._build_model(connection, catalog_model, profile.normalized_params())
        self._cache[cache_key] = model
        return model

    def resolve_catalog_model(
        self, model_id: UUID, *, require_tools: bool = False
    ) -> BaseChatModel:
        """Resolve a **bare catalog model id** to a chat model — no profile/params.

        For ancillary models that aren't agent-configured: the ITEM 2 Slice-C vision
        captioner (and, in principle, any utility model) picks a catalog model
        directly. Uses default (empty) inference params; ``require_tools`` defaults
        ``False`` because vision/utility models need not be tool-callers.

        Raises:
            ModelNotToolCapable: ``require_tools`` and the model can't call tools.
            ConnectionDisabled: the resolved connection is disabled.
            EntityNotFound: the model/connection id does not exist.
        """
        catalog_model = self._catalog.get(model_id)
        if require_tools and not catalog_model.supports_tools:
            raise ModelNotToolCapable(catalog_model.display_name)
        connection = self._connections.get(catalog_model.provider_connection_id)
        if not connection.enabled:
            raise ConnectionDisabled(connection.display_name)
        return self._build_model(connection, catalog_model, NormalizedParams())

    def invalidate(self) -> None:
        """Drop all cached models (call on any connection/catalog/profile edit)."""
        self._cache.clear()

    def _build_model(
        self,
        connection: LLMConnection,
        catalog_model: CatalogModel,
        params: Any,
    ) -> BaseChatModel:
        provider = connection.provider
        api_key = self._secrets.resolve(connection.api_key_ref)
        kwargs: dict[str, Any] = dict(translate_params(provider, params))
        # Reduce a pasted chat/completions endpoint to the API root, else the
        # OpenAI-compatible client double-appends /chat/completions → 404 (Bug 5).
        base = canonical_base_url(connection.base_url)

        if provider == "azure_openai":
            if base:
                kwargs["azure_endpoint"] = base
            if catalog_model.deployment_name:
                kwargs["azure_deployment"] = catalog_model.deployment_name
            if connection.api_version:
                kwargs["api_version"] = connection.api_version
        elif base:
            # openai / anthropic / ollama / openrouter / openai_compatible
            kwargs["base_url"] = base

        if provider not in _NO_API_KEY and api_key:
            kwargs["api_key"] = api_key

        # Turn OFF langchain_openai's per-chunk stream watchdog (default 120s). A
        # per-chunk watchdog cannot tell a reasoning model "thinking" (a long pause
        # before the next chunk) from a hung peer, so it false-trips and aborts
        # live-streamed turns mid-round. Resilience is instead the provider-AGNOSTIC
        # per-turn timeout in the mesh node (``AGENT_TURN_TIMEOUT_S``) — one uniform
        # bound for every provider, not a per-client magic number (R3/R4). Scoped to
        # the OpenAI client only because it is the only one exposing this kwarg.
        if _PROVIDER_MAP[provider] in _OPENAI_FAMILY:
            kwargs.setdefault("stream_chunk_timeout", None)

        # init_chat_model is typed BaseChatModel | _ConfigurableModel; we pass an
        # explicit model_provider (not configurable_fields), so it always returns
        # a concrete BaseChatModel.
        return cast(
            BaseChatModel,
            init_chat_model(
                model=catalog_model.model_identifier,
                model_provider=_PROVIDER_MAP[provider],
                **kwargs,
            ),
        )


def resolve_model(
    resolver: ModelResolver,
    ref: AgentModelRef,
    *,
    require_tools: bool = True,
) -> BaseChatModel:
    """Functional shorthand mirroring the ARCH §9.1 ``resolve_model`` signature."""
    return resolver.resolve(ref, require_tools=require_tools)
