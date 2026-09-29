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
  require_tools, expects_tools)`` and invalidated wholesale on any
  connection/catalog/profile edit (Step 9 will call
  :meth:`ModelResolver.invalidate` on writes).

R1 note — provider mapping
--------------------------
``init_chat_model`` (verified against langchain 1.3.9) natively supports the
provider strings ``openai``, ``anthropic``, ``azure_openai``, ``ollama``,
``openrouter`` — but **not** ``openai_compatible``. An OpenAI-compatible endpoint
*is* the OpenAI client pointed at a custom ``base_url``, so we map
``openai_compatible`` → ``model_provider="openai"`` and pass ``base_url``.

The same applies to ``workbench``: the APIM gateway fronts an Azure-OpenAI-shaped
endpoint, so it is reached with the OpenAI client pointed at a deployment-scoped
``base_url``, with the gateway's headers and an ``api-version`` query parameter.

GPT-5 family handling
---------------------
Before building, :func:`~app.models_layer.model_capabilities.resolve_policy`
decides what the *resolved model* accepts (declared ``model_family`` first, name
detection second). That policy is passed to ``translate_params`` so GPT-5 /
o-series models never receive ``temperature``/``top_p``, and classic models never
receive ``reasoning_effort``/``verbosity``. Where a reasoning model may also bind
tools — which is every mesh agent — the build is routed to the **Responses API**,
the only surface that accepts function tools alongside a reasoning effort.

Whether an endpoint actually *serves* that surface is not guessed from a version
constant: the client is built for the surface the model needs and wrapped in
:class:`~app.models_layer.responses_fallback.ResponsesFallback`, which demotes to
Chat Completions on the endpoint's own refusal and remembers it per deployment.
That is what makes a Workbench or OpenAI-compatible gateway — which typically
exposes only a deployment-scoped ``/chat/completions`` — work with a GPT-5 model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import BaseRateLimiter

from app.core.secrets import SecretResolver
from app.models_layer.base_url import canonical_base_url
from app.models_layer.catalog import CatalogModel, CatalogRepository
from app.models_layer.connections import ConnectionRepository, LLMConnection
from app.models_layer.errors import (
    ConnectionDisabled,
    ModelNotToolCapable,
    NoModelConfigured,
)
from app.models_layer.model_capabilities import (
    TRANSPORT_CHAT,
    TRANSPORT_RESPONSES,
    ParameterPolicy,
    describe_names,
    effort_for_transport,
    resolve_policy,
    resolve_tool_transport,
)
from app.models_layer.profiles import ProfileRepository
from app.models_layer.responses_fallback import (
    ResponsesFallback,
    below_learned_minimum,
    endpoint_key,
    endpoint_of,
    reset_learned_state,
    responses_unsupported,
)
from app.models_layer.translate_params import NormalizedParams, Provider, translate_params
from app.models_layer.workbench import (
    build_workbench_base_url,
    build_workbench_headers,
    validate_workbench_provider,
)

logger = logging.getLogger(__name__)

# Our internal provider enum -> the model_provider string init_chat_model expects.
# ``openai_compatible`` and ``workbench`` need remapping (neither has a native
# init_chat_model branch; both *are* the OpenAI client at a custom base_url).
_PROVIDER_MAP: dict[Provider, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "azure_openai": "azure_openai",
    "ollama": "ollama",
    "openrouter": "openrouter",
    "openai_compatible": "openai",
    "workbench": "openai",
}

# Providers that do not take an api_key (local Ollama). Passing one errors because
# ChatOllama has no api_key field.
_NO_API_KEY: frozenset[str] = frozenset({"ollama"})

# ``init_chat_model`` provider strings backed by the OpenAI client (``ChatOpenAI`` /
# ``AzureChatOpenAI``) — the only ones that accept ``stream_chunk_timeout``.
# ``workbench`` maps to ``openai`` in _PROVIDER_MAP, so it is covered by this set.
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
        rate_limiter: BaseRateLimiter | None = None,
    ) -> None:
        self._connections = connections
        self._catalog = catalog
        self._profiles = profiles
        self._secrets = secrets
        # Shared, run-scoped request pacer injected into every built model so the
        # parallel mesh fan-out cannot burst past the provider's per-minute limit
        # (ARCH §7 / app/models_layer/rate_limit.py). ``None`` ⇒ no pacing.
        self._rate_limiter = rate_limiter
        self._cache: dict[tuple[UUID, UUID, bool, bool], BaseChatModel] = {}

    def resolve(
        self,
        ref: AgentModelRef,
        *,
        require_tools: bool = True,
        expects_tools: bool | None = None,
    ) -> BaseChatModel:
        """Build (or return a cached) chat model for ``ref``.

        Args:
            ref: the agent's profile + optional model override.
            require_tools: enforce the §9.3 tool-calling gate (True for mesh
                agents; False for the Synthesizer / cheap framing models).
            expects_tools: whether tools **may be bound** to this model. Defaults
                to ``require_tools``, which is right for every mesh agent and for
                the Synthesizer. Pass it explicitly where the two differ — a
                caller that relaxes the §9.3 gate but still binds tools (no-team
                chat with an attachment) needs ``expects_tools=True`` so a
                reasoning model is routed to the Responses API, which is the only
                surface accepting tools alongside a reasoning effort.

        Raises:
            NoModelConfigured: neither override nor profile default set a model.
            ModelNotToolCapable: ``require_tools`` and the model can't call tools.
            ConnectionDisabled: the resolved connection is disabled.
            EntityNotFound: a referenced id does not exist.
        """
        binds_tools = require_tools if expects_tools is None else expects_tools
        profile = self._profiles.get(ref.profile_id)
        model_id = ref.override_model_id or profile.default_model_id  # Q1
        if model_id is None:
            raise NoModelConfigured(
                f"profile {profile.name!r} has no default model and no override given"
            )

        # ``binds_tools`` is part of the key because it changes the API surface the
        # client addresses — two callers differing only there must not share one.
        cache_key = (model_id, ref.profile_id, require_tools, binds_tools)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        catalog_model = self._catalog.get(model_id)
        if require_tools and not catalog_model.supports_tools:
            raise ModelNotToolCapable(catalog_model.display_name)  # §9.3 hard gate

        connection = self._connections.get(catalog_model.provider_connection_id)
        if not connection.enabled:
            raise ConnectionDisabled(connection.display_name)

        model = self._build_model(
            connection,
            catalog_model,
            profile.normalized_params(),
            expects_tools=binds_tools,
        )
        self._cache[cache_key] = model
        return model

    def catalog_model_for(self, ref: AgentModelRef) -> CatalogModel:
        """Return the **catalog metadata** an agent ref resolves to — no client built.

        Same selection rule as :meth:`resolve` (override wins over the profile default,
        ARCH Q1), but it stops at the catalog row instead of constructing a chat model.
        The composition root needs this to *compare* models before choosing one — e.g.
        picking the strongest available model to plan with (``supports_reasoning`` /
        ``context_window``) — which would otherwise mean building every candidate just
        to read its declared capabilities.

        Raises:
            NoModelConfigured: neither override nor profile default set a model.
            EntityNotFound: a referenced profile/model id does not exist.
        """
        profile = self._profiles.get(ref.profile_id)
        model_id = ref.override_model_id or profile.default_model_id
        if model_id is None:
            raise NoModelConfigured(
                f"profile {profile.name!r} has no default model and no override given"
            )
        return self._catalog.get(model_id)

    def resolve_catalog_model(
        self,
        model_id: UUID,
        *,
        require_tools: bool = False,
        expects_tools: bool | None = None,
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
        return self._build_model(
            connection,
            catalog_model,
            NormalizedParams(),
            expects_tools=require_tools if expects_tools is None else expects_tools,
        )

    def invalidate(self) -> None:
        """Drop all cached models (call on any connection/catalog/profile edit).

        Also forgets which endpoints refused the Responses surface: a connection
        whose API Version was just raised must be allowed to try the better
        surface again rather than inherit a demotion learned before the edit.
        """
        self._cache.clear()
        reset_learned_state()

    @staticmethod
    def _select_transport(
        policy: ParameterPolicy,
        *,
        provider: str,
        api_version: str | None,
        base_url: str | None,
        deployment: str,
        model: str,
        expects_tools: bool,
        context: str,
    ) -> tuple[str, str]:
        """Pick the API surface, honouring what endpoints have already told us.

        Returns ``(transport, cache_key)``. The surface the model *needs* is
        decided first; it is then downgraded only on evidence gathered from the
        endpoint itself — never on a version constant in this repository
        (:mod:`app.models_layer.responses_fallback`).

        The api-version participates in the key for ``azure_openai`` only, which
        is the one provider whose Responses route is version-addressed.
        """
        # The Responses route is version-scoped on Azure, so the same deployment
        # registered twice on different versions must be probed independently
        # rather than one demoting the other.
        key = endpoint_key(
            base_url,
            deployment,
            model,
            api_version if provider == "azure_openai" else "",
        )

        transport = resolve_tool_transport(
            policy,
            expects_tools=expects_tools,
            provider=provider,
            api_version=api_version,
        )
        if transport != TRANSPORT_RESPONSES:
            return TRANSPORT_CHAT, key

        # An endpoint that has already told us it cannot serve the Responses
        # surface is not asked again: one failed call per deployment per process,
        # never one per run.
        if responses_unsupported(key):
            logger.debug(
                "Responses API already refused by this deployment (%s); using "
                "Chat Completions without asking again.",
                context,
            )
            return TRANSPORT_CHAT, key

        if provider == "azure_openai":
            # Another connection on this same resource has already been told the
            # minimum api-version. If this one is below it the request is known to
            # fail, so it is not sent. The threshold came from the service.
            required = below_learned_minimum(base_url, api_version)
            if required:
                logger.warning(
                    "[RESPONSES] skipping the Responses API for %s: this endpoint "
                    "requires api-version %s or later and this connection states "
                    "%s. Falling back to Chat Completions with reasoning effort "
                    "'none' — THE MODEL WILL NOT REASON, which weakens tool "
                    "selection and answer depth. Raise this connection's API "
                    "Version to %s or later to restore it.",
                    context,
                    required,
                    api_version or "none",
                    required,
                )
                return TRANSPORT_CHAT, key

        return TRANSPORT_RESPONSES, key

    def _build_model(
        self,
        connection: LLMConnection,
        catalog_model: CatalogModel,
        params: Any,
        *,
        expects_tools: bool = True,
    ) -> BaseChatModel:
        provider = connection.provider
        api_key = self._secrets.resolve(connection.api_key_ref)
        # Reduce a pasted chat/completions endpoint to the API root, else the
        # OpenAI-compatible client double-appends /chat/completions → 404 (Bug 5).
        base = canonical_base_url(connection.base_url)

        # Validated up front, before any policy or header work, so a Workbench
        # connection naming a child provider we cannot construct fails fast with
        # a named cause rather than after assembling an unusable request.
        if provider == "workbench":
            validate_workbench_provider(connection.workbench())

        # ── What this MODEL accepts (the GPT-5 family gate) ───────────────────
        # Resolved before translation, because classic-vs-reasoning is a property
        # of the model, not of the profile. Declared ``model_family`` outranks
        # detection — the only way to classify an Azure deployment, whose name
        # the customer chooses and which is what discovery writes into
        # ``model_identifier``.
        policy = resolve_policy(
            provider,
            model=catalog_model.model_identifier,
            deployment_name=catalog_model.deployment_name,
            declared_family=catalog_model.model_family,
        )
        context = describe_names((catalog_model.display_name, catalog_model.model_identifier))
        kwargs: dict[str, Any] = dict(
            translate_params(provider, params, policy=policy, context=context)
        )

        # The deployment identifies the route for Azure and Workbench, and keys the
        # Responses-surface memo for every provider, so it is resolved once here.
        deployment = catalog_model.deployment_name or catalog_model.model_identifier

        if provider == "azure_openai":
            if base:
                kwargs["azure_endpoint"] = base
            if catalog_model.deployment_name:
                kwargs["azure_deployment"] = catalog_model.deployment_name
            if connection.api_version:
                kwargs["api_version"] = connection.api_version
        elif provider == "workbench":
            # The gateway routes on the deployment, which is baked into the path,
            # and takes its api-version as a query parameter rather than a header.
            kwargs["base_url"] = build_workbench_base_url(base, deployment)
            kwargs["default_headers"] = build_workbench_headers(api_key, connection.workbench())
            if connection.api_version:
                kwargs["default_query"] = {"api-version": connection.api_version}
        elif base:
            # openai / anthropic / ollama / openrouter / openai_compatible
            kwargs["base_url"] = base

        if provider not in _NO_API_KEY and api_key:
            kwargs["api_key"] = api_key
        elif provider == "workbench":
            # The gateway authenticates on the Ocp-Apim-Subscription-Key header,
            # not on the OpenAI bearer token — but the OpenAI SDK refuses to
            # construct without *some* api_key, so a sentinel stands in for it.
            # (``build_workbench_headers`` has already refused a truly keyless
            # connection, so this never masks a missing credential.)
            kwargs["api_key"] = "workbench"

        # Turn OFF langchain_openai's per-chunk stream watchdog (default 120s). A
        # per-chunk watchdog cannot tell a reasoning model "thinking" (a long pause
        # before the next chunk) from a hung peer, so it false-trips and aborts
        # live-streamed turns mid-round. Resilience is instead the provider-AGNOSTIC
        # per-turn timeout in the mesh node (``AGENT_TURN_TIMEOUT_S``) — one uniform
        # bound for every provider, not a per-client magic number (R3/R4). Scoped to
        # the OpenAI client only because it is the only one exposing this kwarg.
        if _PROVIDER_MAP[provider] in _OPENAI_FAMILY:
            kwargs.setdefault("stream_chunk_timeout", None)

        # Share the run's request pacer across every model (bounds AGGREGATE mesh
        # throughput, not per-agent — see rate_limit.py). Injected here so the single
        # limiter instance is reused by all cached models this resolver builds.
        if self._rate_limiter is not None:
            kwargs["rate_limiter"] = self._rate_limiter

        # ── Which API surface this build must address ────────────────────────
        # gpt-5.1+ refuse function tools alongside a reasoning effort on Chat
        # Completions and point at /v1/responses instead. Every mesh agent binds
        # tools (the output contract IS a tool call), so this is the default path
        # for a GPT-5 team, not a corner case.
        transport, cache_key = self._select_transport(
            policy,
            provider=provider,
            api_version=connection.api_version,
            base_url=base,
            deployment=deployment,
            model=catalog_model.model_identifier,
            expects_tools=expects_tools,
            context=context,
        )
        stated_effort = kwargs.get("reasoning_effort")

        def construct(surface: str) -> BaseChatModel:
            """Build the client for one API surface.

            The effort is recomputed per surface rather than carried over: Chat
            Completions accepts tools only with no reasoning effort at all, and
            deriving that here means the fallback path cannot inherit a value the
            surface it is falling back to would reject.
            """
            final = dict(kwargs)
            effort = effort_for_transport(
                surface,
                policy,
                stated_effort,
                expects_tools=expects_tools,
                context=context,
            )
            if effort is None:
                final.pop("reasoning_effort", None)
            else:
                final["reasoning_effort"] = effort

            if surface == TRANSPORT_RESPONSES:
                # ``use_responses_api`` is a first-class ChatOpenAI kwarg (verified
                # against langchain_openai 1.3.2); it also translates
                # ``reasoning_effort`` → ``reasoning={"effort": …}`` and
                # ``verbosity`` → ``text.verbosity`` for that surface, so the
                # registrar's settings survive rather than being discarded.
                #
                # ``output_version`` is deliberately NOT set: leaving it at the
                # default keeps the message/content-block shape the AG-UI
                # streaming layer already parses (ARCH §24.6).
                final["use_responses_api"] = True
            else:
                final.pop("use_responses_api", None)

            # init_chat_model is typed BaseChatModel | _ConfigurableModel; we pass
            # an explicit model_provider (not configurable_fields), so it always
            # returns a concrete BaseChatModel.
            return cast(
                BaseChatModel,
                init_chat_model(
                    model=catalog_model.model_identifier,
                    model_provider=_PROVIDER_MAP[provider],
                    **final,
                ),
            )

        client = construct(transport)
        if transport != TRANSPORT_RESPONSES:
            # Classic models, non-gated providers and reasoning models without
            # tools are returned exactly as constructed — nothing that works today
            # changes shape or gains a wrapper.
            return client

        logger.info(
            "Using the Responses API for %s with reasoning effort %r: it is the "
            "only surface that accepts function tools and a reasoning effort "
            "together. Falls back to Chat Completions if this endpoint does not "
            "serve it.",
            context,
            effort_for_transport(
                TRANSPORT_RESPONSES,
                policy,
                stated_effort,
                expects_tools=expects_tools,
                context=context,
            )
            or "provider default",
        )
        # The endpoint is allowed to correct us once, per deployment, per process.
        return cast(
            BaseChatModel,
            ResponsesFallback(
                client,
                lambda: construct(TRANSPORT_CHAT),
                cache_key,
                context,
                endpoint_of(base),
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
