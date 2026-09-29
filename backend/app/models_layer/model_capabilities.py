"""Model parameter capability — which request parameters a chat model accepts.

Why this module exists (RCA)
----------------------------
OpenAI's GPT-5 generation is the first **subtractive** one. Every previous
upgrade (3.5 → 4 → 4o → 4o-mini) accepted the same request body; a reasoning
model rejects ``temperature`` and ``top_p`` outright with a 400, and rejects
``reasoning_effort`` the other way round — a *classic* model answers that
parameter with "Unrecognized request argument".

Before this module, :mod:`app.models_layer.translate_params` decided "is this a
reasoning model?" from ``profile.reasoning_level`` — a **profile-level** setting
the user may leave blank. But classic-vs-reasoning is a **model-level**
property. So a GPT-5 / o-series model under a profile with no reasoning level
was handed the full GPT-4 sampling block. Reproduced against the installed
``langchain_openai`` 1.3.2:

* ``gpt-5`` + ``{temperature, top_p}`` → LangChain drops ``temperature`` (it
  reads the model name) but **``top_p`` survives** → 400.
* ``o3`` → LangChain special-cases only ``o1``, so **both** survive → 400.
* ``azure_openai`` whose catalog ``model_identifier`` is the *deployment* name
  (which is what ``discovery.py`` lists) → the name carries no family signal, so
  **both** survive → 400. This case cannot be fixed by detection at all, which
  is exactly why the declared ``model_family`` override exists.

This module is the SINGLE POINT OF TRUTH for that distinction. Nothing else in
the backend should decide what a model family supports.

Design rules
------------
* The registrar's declaration always outranks detection. An Azure deployment is
  named by the customer, so ``prod-eastus-01`` carries no family signal.
* Detection failing open means CLASSIC. An unknown model keeps the behaviour it
  has today; a false "reasoning" would silently drop a temperature the user set.
* Gating applies only to the OpenAI-schema providers (``openai``,
  ``azure_openai``, ``openai_compatible``, ``workbench``). Anthropic, Ollama and
  OpenRouter construct **byte-identically** to before this module existed.
* Pure functions, no I/O, no mutation. Every helper returns a new value.

Verified (R1, 2026-09): OpenAI model guidance + Azure GPT-5 migration guidance +
the installed ``langchain_openai`` source.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ── Vocabulary ────────────────────────────────────────────────────────────────

PROFILE_CLASSIC = "classic"
"""GPT-4 family and earlier, and every non-gated provider. Full sampling."""

PROFILE_REASONING = "reasoning"
"""GPT-5 family and the o-series. No sampling parameters."""

FAMILY_AUTO = "auto"
FAMILY_GPT4 = "gpt4"
FAMILY_GPT5 = "gpt5"

ModelFamily = Literal["auto", "gpt4", "gpt5"]
MODEL_FAMILY_CHOICES: tuple[str, ...] = (FAMILY_AUTO, FAMILY_GPT4, FAMILY_GPT5)
"""Accepted values of ``model_catalog.model_family``. ``auto`` and absent are
the same thing: detect from the model and deployment names."""

# Only these providers reach an API that enforces the reasoning-model request
# schema. ``workbench`` proxies straight through to an Azure-OpenAI-shaped
# endpoint, so it is gated identically. ``openrouter`` is deliberately NOT here:
# OpenRouter normalises/drops parameters the upstream rejects, and gating it
# would change behaviour that works today (R4 — no silent drift).
GATED_PROVIDERS: frozenset[str] = frozenset(
    {"openai", "azure_openai", "openai_compatible", "workbench"}
)

# ``reasoning_effort`` values the OpenAI-schema providers currently accept.
# ``none`` matters beyond speed: on gpt-5.1 and later a Chat Completions request
# carrying function tools fails unless the effort is none — and it fails even
# when the parameter is omitted, because those models default to one.
REASONING_EFFORT_CHOICES: tuple[str, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

# GPT-5 output-length control (notebook §1). Responses API maps this to
# ``text.verbosity``; Chat Completions accepts it top-level on OpenAI proper.
VERBOSITY_CHOICES: tuple[str, ...] = ("low", "medium", "high")

# Sampling parameters a reasoning model rejects. Only the two this platform can
# actually produce are listed — ``NormalizedParams`` never sets a penalty or a
# logit bias, and enumerating parameters we never send would be dead config.
SAMPLING_PARAMETERS: tuple[str, ...] = ("temperature", "top_p")

# ── Output ceiling for reasoning models ───────────────────────────────────────
#
# ``max_completion_tokens`` on a reasoning model covers reasoning tokens AND
# visible output. A budget that was generous for gpt-4o can therefore be spent
# entirely on thinking and return an EMPTY message with no error at all — which
# in this codebase does not look like a provider problem: an empty contribution
# is read as a confidence-0 abstention (ARCH §21.5), so a too-small budget
# presents as "the agents never contributed".
#
# The floor only ever raises. A larger stated value is a considered choice and
# is never touched. 4096 is the floor Microsoft's GPT-5 migration guidance
# recommends, and it matches ``translate_params.DEFAULT_MAX_TOKENS``.
REASONING_MIN_OUTPUT_TOKENS = 4096

# ── Detection ─────────────────────────────────────────────────────────────────
#
# Matched with word boundaries rather than a bare substring. ``gpt-4o`` must not
# match the ``o4`` family, and a plain ``"o1" in name`` test would fire on any
# name that happens to contain those two characters. Model identifiers are
# free text (an Azure deployment name, an ``org/model`` OpenRouter id, a custom
# gateway alias), so precision here is the difference between a working model
# and a 400.
_REASONING_NAME = re.compile(
    r"(?:^|[^a-z0-9])"  # start, or a non-alphanumeric boundary
    r"(?:gpt-?5|gpt-?6|o[134])"  # gpt-5 / gpt5 / gpt-6 / o1 / o3 / o4
    r"(?![a-z])",  # not the head of a longer word (e.g. "o1x")
    re.IGNORECASE,
)

# ``gpt-5-chat`` and ``gpt-5.1-chat`` are the non-reasoning members of the GPT-5
# family and DO accept temperature. Matched as a family token, not as the word
# "chat" anywhere in the string: a deployment called ``chatbot-gpt-5`` is a
# reasoning model, and treating it as classic would send the parameter that
# fails.
_CHAT_VARIANT = re.compile(r"gpt-?[56](?:\.\d+)?-chat", re.IGNORECASE)


def detect_profile(*names: str | None) -> str:
    """Classify a model from any names known for it.

    Returns ``PROFILE_REASONING`` when any supplied name identifies a
    GPT-5/GPT-6-family or o-series model, ``PROFILE_CLASSIC`` otherwise.

    A catalog row can carry a model identifier, an Azure deployment name or
    both, and for Azure the deployment is usually the only one that says
    anything. ``None`` and blanks are ignored. Never raises.
    """
    for name in names:
        text = str(name or "").strip()
        if not text:
            continue
        if _CHAT_VARIANT.search(text):
            return PROFILE_CLASSIC
        if _REASONING_NAME.search(text):
            return PROFILE_REASONING
    return PROFILE_CLASSIC


def normalize_model_family(value: Any) -> str | None:
    """Read a declared family into a profile, or ``None`` for "detect it".

    Accepts the API vocabulary (``auto`` / ``gpt4`` / ``gpt5``) and the profile
    vocabulary, so a value that round-trips through the DB is still readable.
    Anything unrecognised is treated as *unstated* rather than rejected — this
    is read from a nullable user-set column where a stale or hand-edited value
    must degrade to auto-detection instead of failing a resolution.
    """
    text = str(value or "").strip().lower()
    if not text or text in (FAMILY_AUTO, "detect", "default"):
        return None
    if text in (FAMILY_GPT5, PROFILE_REASONING, "gpt-5", "gpt5+", "o-series"):
        return PROFILE_REASONING
    if text in (FAMILY_GPT4, PROFILE_CLASSIC, "gpt-4", "legacy"):
        return PROFILE_CLASSIC
    logger.debug("Unrecognised model_family %r; falling back to auto-detection.", value)
    return None


def normalize_reasoning_effort(value: Any) -> str | None:
    """A supported ``reasoning_effort`` value, or ``None`` when unusable."""
    text = str(value or "").strip().lower()
    return text if text in REASONING_EFFORT_CHOICES else None


def normalize_verbosity(value: Any) -> str | None:
    """A supported ``verbosity`` value, or ``None`` when unusable."""
    text = str(value or "").strip().lower()
    return text if text in VERBOSITY_CHOICES else None


# ── Policy ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParameterPolicy:
    """What one model accepts, and how that was decided."""

    profile: str
    """``PROFILE_CLASSIC`` or ``PROFILE_REASONING``."""

    gated: bool
    """Whether this provider's schema is enforced at all. False for anthropic,
    ollama and openrouter, which construct exactly as they did before."""

    source: str
    """``declared`` | ``detected`` | ``ungated`` — for logs and traces."""

    @property
    def supports_sampling(self) -> bool:
        """Whether ``temperature`` and ``top_p`` may be sent."""
        return not (self.gated and self.profile == PROFILE_REASONING)

    @property
    def is_reasoning(self) -> bool:
        """Whether this model takes the reasoning request schema."""
        return self.gated and self.profile == PROFILE_REASONING

    def describe(self) -> dict[str, Any]:
        """A trace-safe summary. Carries no credential and no secret."""
        return {
            "profile": self.profile,
            "gated": self.gated,
            "source": self.source,
            "supports_sampling": self.supports_sampling,
        }


CLASSIC_POLICY = ParameterPolicy(profile=PROFILE_CLASSIC, gated=False, source="ungated")
"""The policy for every provider whose schema this module does not gate.

Also the **default** for :func:`app.models_layer.translate_params.translate_params`,
so every pre-existing call site keeps its exact current behaviour (backward
compatibility by construction)."""


def resolve_policy(
    provider: str | None,
    *,
    model: str | None = None,
    deployment_name: str | None = None,
    declared_family: Any = None,
) -> ParameterPolicy:
    """Decide what one model accepts.

    Combines the registrar's declaration with name detection. Detection alone
    cannot classify an Azure deployment, whose name the customer chooses; a
    declaration alone would force every already-registered catalog row to be
    re-edited before it worked.

    Args:
        provider: connection provider slug. Only :data:`GATED_PROVIDERS` gate.
        model: model identifier as the provider knows it.
        deployment_name: Azure deployment name, when there is one.
        declared_family: ``model_catalog.model_family``, if stated.

    Returns:
        A :class:`ParameterPolicy`. Never raises.
    """
    slug = str(provider or "").strip().lower()
    if slug not in GATED_PROVIDERS:
        return CLASSIC_POLICY

    declared = normalize_model_family(declared_family)
    if declared is not None:
        return ParameterPolicy(profile=declared, gated=True, source="declared")

    return ParameterPolicy(
        profile=detect_profile(model, deployment_name),
        gated=True,
        source="detected",
    )


# ── Application ───────────────────────────────────────────────────────────────


def apply_sampling_policy(
    policy: ParameterPolicy,
    kwargs: dict[str, Any],
    *,
    context: str = "",
) -> dict[str, Any]:
    """Return kwargs with unsupported sampling parameters removed.

    Drops ``temperature`` and ``top_p`` when the policy forbids them. A
    reasoning model answers a stated temperature with ``400 Unsupported
    value``; ``top_p`` is never guarded by ``langchain_openai`` at all, and for
    Azure neither is, because ``AzureChatOpenAI`` is addressed by deployment.

    Returns a **new** dict — the input is never mutated, since callers build
    these incrementally and a hidden edit would be invisible at the call site.
    """
    if policy.supports_sampling:
        return kwargs

    dropped = [key for key in SAMPLING_PARAMETERS if kwargs.get(key) is not None]
    if not dropped:
        # Nothing stated — return the input unchanged so an unconfigured build
        # is byte-identical to what it was before this gate existed.
        return kwargs

    logger.info(
        "Reasoning model%s does not accept %s; the stated value(s) are not sent. "
        "Sampling parameters are unsupported on the GPT-5 family and the o-series.",
        f" ({context})" if context else "",
        ", ".join(dropped),
    )
    return {k: v for k, v in kwargs.items() if k not in dropped}


def gated_reasoning_effort(policy: ParameterPolicy, value: Any) -> str | None:
    """The ``reasoning_effort`` to send, or ``None`` to send none.

    Only reasoning models accept the parameter; a classic model answers it with
    "Unrecognized request argument", so a level set on a profile that is later
    pointed at gpt-4o must be **withheld** rather than forwarded.
    """
    if not policy.is_reasoning:
        return None
    return normalize_reasoning_effort(value)


def gated_verbosity(policy: ParameterPolicy, value: Any) -> str | None:
    """The ``verbosity`` to send, or ``None``. GPT-5-family models only.

    Same rule as :func:`gated_reasoning_effort`: a GPT-4-family model rejects
    the parameter, so it is withheld rather than forwarded.
    """
    if not policy.is_reasoning:
        return None
    return normalize_verbosity(value)


def apply_output_floor(
    policy: ParameterPolicy,
    max_tokens: int | None,
    *,
    context: str = "",
) -> int | None:
    """Raise a reasoning model's output budget to a workable floor.

    Returns ``max_tokens`` unchanged unless the policy is reasoning and the
    value is below :data:`REASONING_MIN_OUTPUT_TOKENS`. Only ever **raises**,
    never lowers, and never invents a value where none was stated.

    ``max_completion_tokens`` covers reasoning tokens as well as visible ones,
    so a small budget produces an empty answer and no error — which this
    codebase reads as an abstention, not as a failure (ARCH §21.5).
    """
    if max_tokens is None or not policy.is_reasoning:
        return max_tokens
    if max_tokens >= REASONING_MIN_OUTPUT_TOKENS:
        return max_tokens

    logger.info(
        "Raising the output budget from %d to %d%s: on a reasoning model this "
        "limit covers reasoning tokens as well as the visible answer, and the "
        "stated value can be spent before any output is produced.",
        max_tokens,
        REASONING_MIN_OUTPUT_TOKENS,
        f" ({context})" if context else "",
    )
    return REASONING_MIN_OUTPUT_TOKENS


# ── Transport: which API surface a reasoning model must use for tool calling ──
#
# Newer reasoning models refuse function tools and a reasoning effort together
# on Chat Completions:
#
#   "Function tools with reasoning_effort are not supported for this model in
#    /v1/chat/completions. To use function tools, use /v1/responses or set
#    reasoning_effort to 'none'."
#
# The request fails even when no effort is sent, because gpt-5.1+ models default
# to one. Two routes out, and this platform prefers the first:
#
#   * the **Responses API**, which accepts tools together with the full range of
#     reasoning efforts. ``langchain_openai`` translates ``reasoning_effort``
#     into ``reasoning: {"effort": ...}`` for that surface, so the value the
#     registrar configured is preserved rather than discarded.
#   * ``reasoning_effort="none"``, which keeps Chat Completions working but
#     throws away the reasoning that was asked for.
#
# EVERY mesh agent in this system binds tools — the whole output contract is a
# tool call (``ToolStrategy(ContributionOut)``, app/agents/factory.py) — so this
# is not a corner case, it is the default path for a GPT-5 team.
#
# NOTHING HERE IS KEYED ON A MODEL NAME. The decision derives from the resolved
# profile plus whether tools may be bound, so a reasoning model released next
# month inherits the handling with no code change.

TRANSPORT_CHAT = "chat_completions"
TRANSPORT_RESPONSES = "responses"

# The api-version Azure names in its own refusal, kept for MESSAGING ONLY — it is
# quoted in the hint we show an operator whose endpoint turned the surface down.
# It is deliberately NOT part of any decision; see the block below.
AZURE_MIN_RESPONSES_API_VERSION = "2025-03-01-preview"

# The api-version threshold for the Responses surface is NOT a gate here.
#
# It was, as a constant compared against the connection's api-version, and that
# constant vetoed the better transport without ever asking the endpoint —
# silently stripping a registrar's configured reasoning effort. It was wrong
# three ways:
#
# * It is a **client-side guess about a server capability**. Only the endpoint
#   knows which surfaces it serves, and on a bring-your-own-LLM platform a
#   hardcoded date is wrong for somebody the day it is written.
# * The comparison is a string sort. It works for dated values by luck of
#   formatting and has no defined meaning for a ``preview`` literal.
# * It was silently destructive. Falling back means sending
#   ``reasoning_effort='none'``, so a registrar who configured ``high``
#   unknowingly ran a reasoning model with its reasoning switched off — which is
#   precisely the planning ability that decides whether to call a tool at all.
#
# It was also incomplete: only ``azure_openai`` was gated, so ``workbench`` and
# ``openai_compatible`` gateways — which commonly serve a deployment-scoped
# ``/chat/completions`` and nothing else — had the Responses surface selected
# unconditionally and failed hard with no recovery.
#
# The request is now built for the surface the model actually needs, and the
# endpoint is allowed to correct us **once**, per deployment, per process. See
# :func:`is_responses_unavailable` and ``app.models_layer.responses_fallback``.


def resolve_tool_transport(
    policy: ParameterPolicy,
    *,
    expects_tools: bool,
    provider: str | None = None,
    api_version: str | None = None,
) -> str:
    """Which API surface this build must use.

    ``TRANSPORT_RESPONSES`` when a reasoning model may be given tools,
    ``TRANSPORT_CHAT`` otherwise.

    ``expects_tools`` is deliberately "may bind" rather than "did bind": the
    model is constructed before its tools are known, and the middleware stack
    contributes tools of its own. Over-selecting the Responses API is safe — it
    is the surface these models are designed around, and an endpoint that cannot
    serve it corrects us on the first call — while under-selecting it is a hard
    400 on every call.

    ``provider`` and ``api_version`` are retained for callers and logging. Per
    the block above they no longer influence the decision.
    """
    if not policy.is_reasoning or not expects_tools:
        return TRANSPORT_CHAT
    return TRANSPORT_RESPONSES


def effort_for_transport(
    transport: str,
    policy: ParameterPolicy,
    reasoning_effort: str | None,
    *,
    expects_tools: bool,
    context: str = "",
) -> str | None:
    """The reasoning effort that is safe to send on this transport.

    Returns the stated effort unchanged on the Responses API, and ``"none"``
    when tools must ride on Chat Completions — the only value those models
    accept alongside them. Says so once, at WARNING, because losing the effort a
    user deliberately configured is a behaviour change they are entitled to see
    explained.
    """
    if not policy.is_reasoning or not expects_tools:
        return reasoning_effort

    if transport == TRANSPORT_RESPONSES:
        return reasoning_effort

    if reasoning_effort not in (None, "none"):
        logger.warning(
            "Reasoning effort %r cannot be combined with tools on Chat "
            "Completions%s; sending 'none' for this build. This model will "
            "answer WITHOUT reasoning, which materially weakens tool selection. "
            "Raise the connection's API Version to %s or later so the Responses "
            "API can be used and the configured effort is kept.",
            reasoning_effort,
            f" ({context})" if context else "",
            AZURE_MIN_RESPONSES_API_VERSION,
        )
    # Explicit ``none`` is required, not merely omitted: gpt-5.1+ models default
    # to a non-zero effort, so sending nothing fails exactly as "high" does.
    return "none"


# ── Runtime correction: letting the endpoint tell us what it serves ───────────
#
# Everything above decides what to *send*. The three detectors below read what
# came *back*, so a wrong guess costs one call instead of every call.
#
# All of them are keyed on the provider's own words rather than on a model name,
# because the SDK raises one exception class for every 400 — and because a model
# released next month reports the same constraint in the same sentence while
# matching no table in this repository.

# What the provider says when tools and a reasoning effort are refused together.
_TOOL_REASONING_MARKERS: tuple[str, ...] = (
    "function tools with reasoning_effort",
    "reasoning_effort to 'none'",
    "/v1/responses",
)

# What an endpoint says when it cannot serve the Responses surface at all — an
# older Azure resource, an api-version that predates it, or a gateway that only
# ever exposed a deployment-scoped /chat/completions route.
_RESPONSES_UNAVAILABLE_MARKERS: tuple[str, ...] = (
    "unknown path",
    "resource not found",
    "invalid url",
    "api version not supported",
    "unsupported api version",
    "does not support the responses api",
    "/responses",
    "no route",
)

# Statuses that mean "this surface is not here" on their own, with no message
# needed. A bare 400 is NOT among them — a 400 usually means the surface was
# reached and rejected the body, and demoting on every 400 would silently
# downgrade a model whose request merely had a bad field.
_RESPONSES_UNAVAILABLE_STATUSES: tuple[int, ...] = (404, 405)

# Azure refuses an unsupported Responses surface with **400**, not 404:
#
#   400 BadRequest — "Azure OpenAI Responses API is enabled only for
#                     api-version 2025-03-01-preview and later"
#
# Azure writes "Responses API" with a space, so none of the routing-shaped
# markers above match it. The signature is deliberately conjunctive: the message
# must name the Responses surface AND talk about api-version support, so a
# body-validation 400 mentioning neither still surfaces to the caller.
_RESPONSES_SURFACE_PHRASES: tuple[str, ...] = ("responses api", "/responses")
_RESPONSES_VERSION_PHRASES: tuple[str, ...] = (
    "api-version",
    "api version",
    "is enabled only for",
    "not supported",
    "unsupported",
)

# Any api-version-shaped token: a date, optionally suffixed (``-preview``, ``-ga``).
# Read out of the service's own refusal so the threshold is never guessed.
_API_VERSION_IN_MESSAGE = re.compile(r"\b(\d{4}-\d{2}-\d{2}(?:-[a-z]+)?)\b", re.IGNORECASE)


def is_responses_unavailable(exc: BaseException) -> bool:
    """Whether a failure means this endpoint does not serve the Responses API.

    Recognises "that surface is not available here", **not** "your request was
    wrong". Whether an endpoint serves ``/responses`` is a property of the
    deployment and its api-version, and only the service can answer it; asking
    and remembering is self-maintaining, where a pinned version constant ages
    badly.

    Returns ``False`` for anything ambiguous — a false positive downgrades a
    model that was working, so the bar stays high.
    """
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in _RESPONSES_UNAVAILABLE_STATUSES:
        return True

    message = str(exc).lower()
    if any(marker in message for marker in _RESPONSES_UNAVAILABLE_MARKERS):
        return True

    # The Azure case: a 400 that names both the surface and the version rule.
    names_surface = any(phrase in message for phrase in _RESPONSES_SURFACE_PHRASES)
    names_version = any(phrase in message for phrase in _RESPONSES_VERSION_PHRASES)
    return bool(names_surface and names_version)


def learned_min_responses_version(exc: BaseException) -> str | None:
    """The minimum api-version the service named in its refusal, or ``None``.

    Azure's message is *"Azure OpenAI Responses API is enabled only for
    api-version 2025-03-01-preview and later"* — the answer is in the complaint.
    Extracting it lets every other connection on that endpoint skip a doomed
    request, without a threshold ever being written into this repository.

    Returns the newest version named: a message mentioning several is stating a
    range, and the upper bound is the requirement.
    """
    try:
        found = _API_VERSION_IN_MESSAGE.findall(str(exc))
    except Exception:  # noqa: BLE001 — parsing must never fail a call
        return None
    if not found:
        return None
    # Dated versions sort correctly as strings, which is what makes max() right.
    return max(str(value).lower() for value in found)


def is_tool_reasoning_conflict(exc: BaseException) -> bool:
    """Whether a failure is the tools-plus-reasoning refusal.

    Used to explain the failure in terms of the setting that caused it, rather
    than showing an operator a raw 400 with nothing connecting it to the
    Reasoning Effort they chose.
    """
    message = str(exc).lower()
    return any(marker in message for marker in _TOOL_REASONING_MARKERS)


def explain_model_failure(exc: BaseException) -> str:
    """Turn a provider failure into something the reader can act on.

    Recognises the failures this layer knows how to explain and returns a
    sentence naming the setting to change; falls back to the original message for
    everything else, so nothing is ever hidden.
    """
    if is_tool_reasoning_conflict(exc):
        return (
            "this model does not accept a reasoning effort together with tools on "
            "the Chat Completions API. Set the connection's API Version to "
            f"{AZURE_MIN_RESPONSES_API_VERSION} or later so the Responses API can "
            "be used, or set Reasoning Level to 'none' on the inference profile."
        )
    return str(exc)


def describe_names(names: tuple[str | None, ...]) -> str:
    """The first non-blank name, for log context. Never returns ``None``."""
    for name in names:
        text = str(name or "").strip()
        if text:
            return text
    return "unnamed model"


__all__ = [
    "AZURE_MIN_RESPONSES_API_VERSION",
    "CLASSIC_POLICY",
    "FAMILY_AUTO",
    "FAMILY_GPT4",
    "FAMILY_GPT5",
    "GATED_PROVIDERS",
    "MODEL_FAMILY_CHOICES",
    "PROFILE_CLASSIC",
    "PROFILE_REASONING",
    "REASONING_EFFORT_CHOICES",
    "REASONING_MIN_OUTPUT_TOKENS",
    "SAMPLING_PARAMETERS",
    "TRANSPORT_CHAT",
    "TRANSPORT_RESPONSES",
    "VERBOSITY_CHOICES",
    "ModelFamily",
    "ParameterPolicy",
    "apply_output_floor",
    "apply_sampling_policy",
    "describe_names",
    "detect_profile",
    "effort_for_transport",
    "explain_model_failure",
    "gated_reasoning_effort",
    "gated_verbosity",
    "is_responses_unavailable",
    "is_tool_reasoning_conflict",
    "learned_min_responses_version",
    "normalize_model_family",
    "normalize_reasoning_effort",
    "normalize_verbosity",
    "resolve_policy",
    "resolve_tool_transport",
]
