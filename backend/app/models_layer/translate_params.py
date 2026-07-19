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
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models_layer.errors import UnknownProvider

# Our internal provider enum (matches llm_connections.provider — TECHNICAL §11.3).
Provider = Literal[
    "openai",
    "anthropic",
    "azure_openai",
    "ollama",
    "openrouter",
    "openai_compatible",
]

ReasoningLevel = Literal["low", "medium", "high"]

# Providers whose client is OpenAI-shaped (same kwargs, same reasoning_effort).
_OPENAI_FAMILY: frozenset[str] = frozenset({"openai", "openai_compatible", "azure_openai"})

# reasoning level -> Anthropic extended-thinking token budget.
# Anthropic requires budget_tokens >= 1024 and strictly < max_tokens.
_ANTHROPIC_THINKING_BUDGET: dict[ReasoningLevel, int] = {
    "low": 1024,
    "medium": 4096,
    "high": 8192,
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
    # Ollama-only context window override; model-fixed for hosted providers (§9.2).
    num_ctx: int | None = Field(default=None, gt=0)
    # json_mode is honoured at the agent layer via create_agent(response_format=...)
    # (ARCH §22.3), NOT as an init_chat_model kwarg — so it is intentionally not
    # translated here. Kept on the model for completeness/round-tripping.
    json_mode: bool = False


def translate_params(provider: Provider, params: NormalizedParams) -> dict[str, Any]:
    """Map normalized params to ``provider``'s accepted ``init_chat_model`` kwargs.

    Returns only the kwargs that ``provider`` accepts; everything unsupported is
    dropped rather than passed through (which would error at request time).

    Raises:
        UnknownProvider: if ``provider`` is outside the supported set.
    """
    if provider in _OPENAI_FAMILY or provider == "openrouter":
        # OpenRouter is OpenAI-shaped (ChatOpenRouter accepts the same kwargs).
        return _translate_openai_family(params)
    if provider == "anthropic":
        return _translate_anthropic(params)
    if provider == "ollama":
        return _translate_ollama(params)
    raise UnknownProvider(provider)


def _translate_openai_family(params: NormalizedParams) -> dict[str, Any]:
    """OpenAI / OpenAI-compatible / Azure OpenAI / OpenRouter (all OpenAI-shaped)."""
    out: dict[str, Any] = {}
    if params.reasoning_level is not None:
        # Reasoning models accept reasoning_effort and reject temperature/top_p.
        out["reasoning_effort"] = params.reasoning_level
    else:
        if params.temperature is not None:
            out["temperature"] = params.temperature
        if params.top_p is not None:
            out["top_p"] = params.top_p
    # Always send a completion cap: explicit profile value, else the default floor
    # (prevents reserving the model's full window — see DEFAULT_MAX_TOKENS).
    out["max_tokens"] = params.max_tokens if params.max_tokens is not None else DEFAULT_MAX_TOKENS
    return out


def _translate_anthropic(params: NormalizedParams) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if params.reasoning_level is not None:
        budget = _ANTHROPIC_THINKING_BUDGET[params.reasoning_level]
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
