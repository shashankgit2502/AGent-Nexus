"""Let the endpoint correct a Responses-API build it cannot actually serve.

Why this module exists (RCA)
----------------------------
A reasoning model that may be given tools must use the **Responses API** — it is
the only surface that accepts function tools alongside a reasoning effort
(:mod:`app.models_layer.model_capabilities`). But whether a given endpoint
*serves* that surface is a fact only the endpoint holds:

* an older Azure resource, or an api-version predating ``/openai/responses``;
* a ``workbench`` / ``openai_compatible`` gateway that exposes a
  deployment-scoped ``/chat/completions`` route and nothing else.

The previous design guessed this from the connection's ``api_version`` against a
hardcoded constant. That guess was wrong in both directions: it vetoed the better
transport for Azure connections that would have worked (silently stripping the
configured reasoning effort), and it never applied to Workbench or
OpenAI-compatible gateways at all, so those had the Responses surface selected
unconditionally and failed hard on every call with no recovery.

So the request is built for the surface the model needs, and the endpoint is
allowed to correct us **once**. Demotion is remembered per deployment, so the
cost is one failed call per process — never one per run.

Design
------
* The wrapper delegates by ``__getattr__`` and returns a **new wrapper** from
  ``bind_tools``, so the fallback survives tool binding — which is exactly where
  it is needed, since tools are what force this surface.
* What is learned is recorded against the *endpoint*, not the connection, so a
  second connection on the same resource skips a request already known to fail.
* The api-version threshold is never declared here. The service states it in its
  own refusal and :func:`~app.models_layer.model_capabilities.learned_min_responses_version`
  reads it back out, so if the threshold moves the next refusal teaches us.

Ported from the reference implementation ``echolib/llm_client_builder_v2.py``
(``_ResponsesFallback``, ``_endpoint_key``, ``_below_learned_minimum``) — the
control flow and the learning behaviour are reproduced rather than reinvented.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

from app.models_layer.model_capabilities import (
    is_responses_unavailable,
    learned_min_responses_version,
)

logger = logging.getLogger(__name__)

# Deployment keys (endpoint + deployment + api-version) that have already told us
# they cannot serve the Responses surface. Process-scoped: a deliberate cache, not
# persisted state — a resource upgraded tomorrow simply starts working again after
# a restart, with no migration and no release.
_RESPONSES_UNSUPPORTED: set[str] = set()

# Endpoint -> the minimum api-version that endpoint said it needs for the
# Responses surface. Populated from the service's own refusal, never declared.
# This is what turns one failed call into knowledge for the whole endpoint.
_RESPONSES_MIN_VERSION: dict[str, str] = {}

_SENTINEL = object()


def endpoint_of(base_url: str | None) -> str:
    """The resource a deployment belongs to. Carries no secret."""
    return (base_url or "").rstrip("/")


def endpoint_key(
    base_url: str | None,
    deployment: str | None,
    model: str | None,
    api_version: str | None = "",
) -> str:
    """Cache key for one deployment **at one api-version**. Carries no secret.

    The api-version is part of the key, not incidental to it. Whether an endpoint
    serves ``/responses`` is decided by the *route*, and the route is
    ``{endpoint}/openai/responses?api-version={version}`` — so the same
    deployment genuinely answers differently on two versions.

    Keying on endpoint and deployment alone would be wrong in the case that
    actually occurs: one model deployed once, registered twice with different
    api-versions. The connection on the older version fails the probe, and a key
    without the version would demote the *other* connection too — silently
    stripping the reasoning effort from a registration that was correct.
    """
    return "::".join(
        (
            endpoint_of(base_url),
            (deployment or model or ""),
            (api_version or "").strip(),
        )
    )


def responses_unsupported(key: str) -> bool:
    """Whether this deployment has already refused the Responses surface."""
    return key in _RESPONSES_UNSUPPORTED


def below_learned_minimum(base_url: str | None, api_version: str | None) -> str | None:
    """The required api-version when this connection is known to be below it.

    Dated api-versions sort correctly as strings, which is what makes the
    comparison meaningful. ``None`` means either nothing has been learned for this
    endpoint or the connection already meets the requirement — in both cases the
    request goes ahead and the service remains the authority.
    """
    required = _RESPONSES_MIN_VERSION.get(endpoint_of(base_url))
    if not required:
        return None
    current = (api_version or "").strip().lower()
    if not current:
        # No version stated at all. OpenAI proper sends none and is unaffected;
        # for Azure the SDK supplies its own default, so this is not a case where
        # skipping can be justified on what we know.
        return None
    return required if current < required else None


def reset_learned_state() -> None:
    """Forget every demotion and learned threshold.

    Called when the model layer is edited, alongside the resolver's cache
    invalidation: a connection whose api-version was just raised must be allowed
    to try the better surface again instead of inheriting a stale demotion.
    """
    _RESPONSES_UNSUPPORTED.clear()
    _RESPONSES_MIN_VERSION.clear()


class ResponsesFallback:
    """A chat model that demotes to Chat Completions if Responses isn't served.

    Delegates everything it does not override to the wrapped model, so it is a
    drop-in for a ``BaseChatModel`` at every call site (LangChain's agent
    middleware treats the model structurally — ``ModelRequest`` is a plain
    dataclass and calls ``bind_tools`` duck-typed — so no subclassing is needed).

    Only ``bind_tools`` and the four invocation methods are overridden. Anything
    else (``with_config``, ``with_retry``, …) delegates and returns the
    underlying object; those paths do not carry the fallback, which is acceptable
    because they are not how an agent turn reaches the provider.
    """

    def __init__(
        self,
        llm: Any,
        rebuild: Any,
        key: str,
        context: str = "",
        endpoint: str = "",
    ) -> None:
        self._llm = llm
        self._rebuild = rebuild
        self._key = key
        self._context = context
        self._endpoint = endpoint

    def __getattr__(self, name: str) -> Any:
        # Only consulted for attributes not found normally, so the wrapper's own
        # fields never reach here. The guard keeps a missing ``_llm`` (e.g. during
        # copy/unpickle, before __init__ has run) from recursing forever.
        if name.startswith("__") or name == "_llm":
            raise AttributeError(name)
        return getattr(self._llm, name)

    def bind_tools(self, *args: Any, **kwargs: Any) -> ResponsesFallback:
        """Bind tools on both the live client and the rebuild path.

        Returning a wrapper (rather than the bound model) is what makes the
        fallback survive binding — and binding is precisely what forces the
        Responses surface, so an unwrapped result here would defeat the module.
        """

        def bound_rebuild() -> Any:
            return self._rebuild().bind_tools(*args, **kwargs)

        return ResponsesFallback(
            self._llm.bind_tools(*args, **kwargs),
            bound_rebuild,
            self._key,
            self._context,
            self._endpoint,
        )

    def _demote(self, exc: BaseException) -> bool:
        """Swap to a Chat Completions client. ``False`` when this isn't that failure.

        A failure that is not "this surface is not here" is re-raised untouched,
        so a genuine request error stays visible instead of being masked by a
        silent retry (R3 — no swallowing exceptions).
        """
        if not is_responses_unavailable(exc):
            return False

        _RESPONSES_UNSUPPORTED.add(self._key)

        # The service usually names the api-version it requires. Recording it
        # against the endpoint lets every other connection on an older version
        # skip this request entirely instead of each discovering it the hard way —
        # and it is the service's number, never one written here.
        required = learned_min_responses_version(exc)
        if required and self._endpoint:
            if _RESPONSES_MIN_VERSION.get(self._endpoint) != required:
                _RESPONSES_MIN_VERSION[self._endpoint] = required
                logger.warning(
                    "[RESPONSES] %s requires api-version %s or later for the "
                    "Responses API. Learned from the service; connections below "
                    "that version will now skip it without a failed call.",
                    self._endpoint,
                    required,
                )

        logger.warning(
            "[RESPONSES] %s cannot use the Responses API on this connection "
            "(%s). Falling back to Chat Completions with reasoning effort "
            "'none' for the rest of this process. Tool calling will work, but "
            "THE MODEL WILL NOT REASON before answering, which materially "
            "weakens tool selection and answer depth. Raise this connection's "
            "API Version%s to restore it.",
            self._context or "this model",
            type(exc).__name__,
            f" to {required} or later" if required else "",
        )
        self._llm = self._rebuild()
        return True

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._llm.invoke(*args, **kwargs)
        except Exception as exc:
            if not self._demote(exc):
                raise
            return self._llm.invoke(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return await self._llm.ainvoke(*args, **kwargs)
        except Exception as exc:
            if not self._demote(exc):
                raise
            return await self._llm.ainvoke(*args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        # The failure surfaces on the first chunk, not at call time, so the first
        # item is pulled inside the guard and replayed afterwards.
        try:
            iterator = self._llm.stream(*args, **kwargs)
            first = next(iterator, _SENTINEL)
        except Exception as exc:
            if not self._demote(exc):
                raise
            yield from self._llm.stream(*args, **kwargs)
            return

        if first is not _SENTINEL:
            yield first
        yield from iterator

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        try:
            agen = self._llm.astream(*args, **kwargs)
            first = await agen.__anext__()
        except StopAsyncIteration:
            return
        except Exception as exc:
            if not self._demote(exc):
                raise
            async for chunk in self._llm.astream(*args, **kwargs):
                yield chunk
            return

        yield first
        async for chunk in agen:
            yield chunk


__all__ = [
    "ResponsesFallback",
    "below_learned_minimum",
    "endpoint_key",
    "endpoint_of",
    "reset_learned_state",
    "responses_unsupported",
]
