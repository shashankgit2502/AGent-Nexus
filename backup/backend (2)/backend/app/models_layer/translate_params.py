"""Per-provider parameter translation (ARCHITECTURE.md §9.2 / §27.5).

Why this module is load-bearing
--------------------------------
Inference parameters are **not portable across providers** (ARCH §9.2). An
inference profile stores *normalized* params (temperature, top_p, max_tokens, a
reasoning level, json mode); each provider accepts a *different* kwarg shape and
**rejects** params it does not understand. Splatting the normalized dict blindly
into every provider's client therefore raises validation/HTTP errors at request
time. `translate_params` is the single place that maps the normalized params to
each provider's accepted kwargs and **drops** the rest.

ARCH §20 note 3 flags this as the highest-bug-risk function in the layer — it is
unit-tested per provider in ``tests/models_layer/test_translate_params.py``.

Verified kwarg names (R1, against installed langchain 1.3.9 / providers)
------------------------------------------------------------------------
* ``ChatOpenAI``     : temperature, top_p, max_tokens, reasoning_effort
* ``ChatAnthropic``  : temperature, top_p, max_tokens, thinking
* ``ChatOllama``     : temperature, top_p, num_ctx  (NO max_tokens, NO api_key)
* ``ChatOpenRouter`` : temperature, top_p, max_tokens  (OpenAI-shaped)

The two non-obvious rules, both straight from §9.2 ("temperature ... rejected by
some reasoning models") and the provider APIs:

1. **OpenAI-family reasoning models reject ``temperature``/``top_p``.** When a
   reasoning level is requested we send ``reasoning_effort`` and drop sampling.
2. **Anthropic extended thinking requires ``temperature`` unset (effectively 1)
   and a ``max_tokens`` strictly greater than the thinking budget.** When a
   reasoning level is requested we send ``thinking={...}``, bump ``max_tokens``
   above the budget, and drop sampling.

GPT-5 family gate (``policy``) — RCA
------------------------------------
Rule 1 above was keyed on ``params.reasoning_level``, a **profile-level** flag
the user may leave blank — but classic-vs-reasoning is a **model-level**
property. A GPT-5 / o-series model under a profile with no reasoning level was
therefore handed the full GPT-4 sampling block, and the SDK only rescues part of
it (it drops ``temperature`` by model name, never ``top_p``, and never anything
for Azure, which is addressed by deployment). The fix is the ``policy``
argument: :mod:`app.models_layer.model_capabilities` resolves the model's family
once — declared ``model_family`` first, name detection second — and this module
filters against that instead of guessing from the profile.

``policy`` is keyword-only and defaults to ``CLASSIC_POLICY``, so every
pre-existing call site keeps its exact current behaviour.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models_layer.errors import UnknownProvider
from app.models_layer.model_capabilities import (
    CLASSIC_POLICY,
    ParameterPolicy,
    apply_output_floor,
    apply_sampling_policy,
    gated_reasoning_effort,
    gated_verbosity,
)

# Our internal provider enum (matches llm_connections.provider — TECHNICAL §11.3).
Provider = Literal[
    "openai",
    "anthropic",
    "azure_openai",
    "ollama",
    "openrouter",
    "openai_compatible",
    # APIM-fronted gateway proxying to an Azure-OpenAI-shaped endpoint. Reached
    # with the OpenAI client (deployment-scoped base_url + gateway headers), so
    # it shares the OpenAI kwarg shape and the GPT-5 schema gate.
    "workbench",
]

# The full GPT-5 vocabulary. ``minimal`` arrived with GPT-5; ``none``/``xhigh``/
# ``max`` with GPT-5.1+ (where ``none`` is frequently the model default, so an
# explicit level is required to get reasoning at all). The legacy
# ``low``/``medium``/``high`` values are unchanged, so existing profiles are
# valid as written.
ReasoningLevel = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]

# GPT-5 output-length control (notebook §1): scales length and depth without
# rewriting the prompt. Reasoning models only.
Verbosity = Literal["low", "medium", "high"]

# Providers whose client is OpenAI-shaped (same kwargs, same reasoning_effort).
_OPENAI_FAMILY: frozenset[str] = frozenset(
    {"openai", "openai_compatible", "azure_openai", "workbench"}
)

# reasoning level -> Anthropic extended-thinking token budget.
# Anthropic requires budget_tokens >= 1024 and strictly < max_tokens.
#
# Covers the FULL ReasoningLevel vocabulary, not just the original three. The
# literal was widened for the GPT-5 family (``none``/``minimal``/``xhigh``/
# ``max``), and a profile carrying one of those can still be pointed at an
# Anthropic model — a partial map would raise ``KeyError`` mid-resolution.
# ``none`` is absent on purpose: it means "do not think", handled below by
# taking the non-reasoning branch.
_ANTHROPIC_THINKING_BUDGET: dict[str, int] = {
    "minimal": 1024,
    "low": 1024,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
    "max": 24576,
}
# Headroom added on top of the thinking budget so the model can still answer.
_ANTHROPIC_ANSWER_HEADROOM = 4096

# Default completion cap applied when a profile leaves ``max_tokens`` unset, for
# providers that meter/charge against it (OpenAI-family + OpenRouter, and
# Anthropic non-reasoning). Rationale (regression guard): an unset cap lets the
# provider reserve the model's *full* output window. OpenRouter bills that
# reserved amount up-front against the account balance and rejects the request
# with ``PaymentRequiredResponseError`` when the balance can't cover it (observed:
# "requested up to 65536 tokens, but can only afford 9983"). A modest explicit
# floor keeps an unconfigured profile from silently reserving 64K. Profiles may
# still set any explicit value; this only fills the gap. Tune here if needed.
DEFAULT_MAX_TOKENS = 4096


class NormalizedParams(BaseModel):
    """Provider-agnostic inference params as stored on an inference profile.

    Frozen (immutable) per the project coding style: translation never mutates
    the source; it returns a fresh provider-specific kwargs dict.
    """

    model_config = ConfigDict(frozen=True)

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0)
    reasoning_level: ReasoningLevel | None = None
    # GPT-5 verbosity (notebook §1). Sent only to a reasoning model; a GPT-4
    # model rejects the parameter, so it is gated like reasoning_effort.
    verbosity: Verbosity | None = None
    # Ollama-only context window override; model-fixed for hosted providers (§9.2).
    num_ctx: int | None = Field(default=None, gt=0)
    # json_mode is honoured at the agent layer via create_agent(response_format=...)
    # (ARCH §22.3), NOT as an init_chat_model kwarg — so it is intentionally not
    # translated here. Kept on the model for completeness/round-tripping.
    json_mode: bool = False


def translate_params(
    provider: Provider,
    params: NormalizedParams,
    *,
    policy: ParameterPolicy = CLASSIC_POLICY,
    context: str = "",
) -> dict[str, Any]:
    """Map normalized params to ``provider``'s accepted ``init_chat_model`` kwargs.

    Returns only the kwargs that ``provider`` accepts; everything unsupported is
    dropped rather than passed through (which would error at request time).

    Args:
        provider: the connection's provider slug.
        params: the profile's normalized params.
        policy: what the *resolved model* accepts
            (:func:`app.models_layer.model_capabilities.resolve_policy`).
            Defaults to ``CLASSIC_POLICY`` — full sampling, no reasoning
            parameters — which is exactly the behaviour every caller had before
            this argument existed.
        context: a model name used only for log messages.

    Raises:
        UnknownProvider: if ``provider`` is outside the supported set.
    """
    if provider in _OPENAI_FAMILY or provider == "openrouter":
        # OpenRouter is OpenAI-shaped (ChatOpenRouter accepts the same kwargs).
        return _translate_openai_family(params, policy, context)
    if provider == "anthropic":
        return _translate_anthropic(params)
    if provider == "ollama":
        return _translate_ollama(params)
    raise UnknownProvider(provider)


def _translate_openai_family(
    params: NormalizedParams, policy: ParameterPolicy, context: str
) -> dict[str, Any]:
    """OpenAI / OpenAI-compatible / Azure / Workbench / OpenRouter (OpenAI-shaped).

    Built in two passes on purpose. The first states what the *profile* asked
    for; the second filters it against what the *model* accepts. Keeping them
    separate is what makes the gate total: a parameter cannot slip through by
    being set on a path the gate does not inspect.
    """
    if not policy.gated:
        # UNGATED (openrouter). We have no model-family signal we trust here, so
        # the profile's declaration stays authoritative exactly as it was before
        # the policy argument existed — OpenRouter normalises/drops whatever the
        # upstream rejects, and a gate here would silently strip a reasoning
        # effort that works today (R4: no un-asked-for behaviour change).
        return _translate_openai_legacy(params)

    out: dict[str, Any] = {}

    # Pass 1 — what the profile stated.
    if params.temperature is not None:
        out["temperature"] = params.temperature
    if params.top_p is not None:
        out["top_p"] = params.top_p

    # A reasoning level on the profile still means "this run wants reasoning",
    # but whether the *model* can be told so is the policy's call: a classic
    # model answers ``reasoning_effort`` with "Unrecognized request argument".
    effort = gated_reasoning_effort(policy, params.reasoning_level)
    if effort is not None:
        out["reasoning_effort"] = effort
    verbosity = gated_verbosity(policy, params.verbosity)
    if verbosity is not None:
        out["verbosity"] = verbosity

    # Always send a completion cap: explicit profile value, else the default floor
    # (prevents reserving the model's full window — see DEFAULT_MAX_TOKENS).
    # ``ChatOpenAI``/``AzureChatOpenAI`` rename this to ``max_completion_tokens``
    # on the wire (verified against langchain_openai 1.3.2), which is what a
    # reasoning model requires.
    max_tokens = params.max_tokens if params.max_tokens is not None else DEFAULT_MAX_TOKENS
    # On a reasoning model that budget also pays for the thinking tokens, so a
    # value sized for the visible answer alone returns empty content — which this
    # system reads as an abstention, not as an error (ARCH §21.5).
    out["max_tokens"] = apply_output_floor(policy, max_tokens, context=context)

    # Pass 2 — drop what the model rejects. GPT-5 / o-series reject BOTH
    # sampling parameters; the SDK guards only ``temperature``, only by model
    # name, so ``top_p`` and every Azure deployment fall through to a 400.
    return apply_sampling_policy(policy, out, context=context)


def _translate_openai_legacy(params: NormalizedParams) -> dict[str, Any]:
    """The pre-policy translation, kept verbatim for ungated providers.

    Preserved as its own function rather than as a branch so it is obvious that
    nothing about the OpenRouter path changed, and so a future gating decision
    is a one-line move rather than a rewrite.
    """
    out: dict[str, Any] = {}
    if params.reasoning_level is not None:
        out["reasoning_effort"] = params.reasoning_level
    else:
        if params.temperature is not None:
            out["temperature"] = params.temperature
        if params.top_p is not None:
            out["top_p"] = params.top_p
    out["max_tokens"] = params.max_tokens if params.max_tokens is not None else DEFAULT_MAX_TOKENS
    return out


def _translate_anthropic(params: NormalizedParams) -> dict[str, Any]:
    # ``none`` means "no reasoning", so it takes the plain sampling branch — the
    # same place an unset level goes. Any other level maps to a thinking budget.
    budget = _ANTHROPIC_THINKING_BUDGET.get(params.reasoning_level or "")
    out: dict[str, Any] = {}
    if budget is not None:
        out["thinking"] = {"type": "enabled", "budget_tokens": budget}
        # max_tokens must strictly exceed the thinking budget; ensure headroom.
        requested = params.max_tokens or 0
        out["max_tokens"] = max(requested, budget + _ANTHROPIC_ANSWER_HEADROOM)
        # extended thinking pins temperature to 1 and forbids top_p → drop both.
    else:
        if params.temperature is not None:
            out["temperature"] = params.temperature
        if params.top_p is not None:
            out["top_p"] = params.top_p
        # Same default-floor rule as the OpenAI family (Anthropic also bills the
        # reserved output) — explicit value wins, else DEFAULT_MAX_TOKENS.
        out["max_tokens"] = (
            params.max_tokens if params.max_tokens is not None else DEFAULT_MAX_TOKENS
        )
    return out


def _translate_ollama(params: NormalizedParams) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if params.temperature is not None:
        out["temperature"] = params.temperature
    if params.top_p is not None:
        out["top_p"] = params.top_p
    # Ollama's context window is a request param (num_ctx); hosted providers fix it.
    if params.num_ctx is not None:
        out["num_ctx"] = params.num_ctx
    # Ollama has no max_tokens kwarg (uses num_predict) and reasoning is n/a (§9.2)
    # → both intentionally dropped.
    return out
