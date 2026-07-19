"""Per-provider tests for ``translate_params`` (ARCH §9.2/§27.5).

This is the highest-bug-risk function in the model layer (ARCH §20 note 3), so it
is exercised per provider against the *real* kwarg shapes the clients accept
(verified against langchain 1.3.9 at build time, R1).
"""

from __future__ import annotations

import pytest

from app.models_layer.errors import UnknownProvider
from app.models_layer.translate_params import (
    DEFAULT_MAX_TOKENS,
    NormalizedParams,
    translate_params,
)

# A profile with plain sampling params (no reasoning).
SAMPLING = NormalizedParams(temperature=0.4, top_p=0.9, max_tokens=512)
# A profile asking for reasoning.
REASONING = NormalizedParams(reasoning_level="high", temperature=0.4, top_p=0.9, max_tokens=512)


# ── OpenAI family (openai / openai_compatible / azure_openai) ────────────────


@pytest.mark.parametrize("provider", ["openai", "openai_compatible", "azure_openai"])
def test_openai_family_sampling(provider: str) -> None:
    out = translate_params(provider, SAMPLING)  # type: ignore[arg-type]
    assert out == {"temperature": 0.4, "top_p": 0.9, "max_tokens": 512}


@pytest.mark.parametrize("provider", ["openai", "openai_compatible", "azure_openai"])
def test_openai_family_reasoning_drops_sampling(provider: str) -> None:
    """Reasoning models reject temperature/top_p → only reasoning_effort survives."""
    out = translate_params(provider, REASONING)  # type: ignore[arg-type]
    assert out == {"reasoning_effort": "high", "max_tokens": 512}
    assert "temperature" not in out
    assert "top_p" not in out


# ── OpenRouter (OpenAI-shaped) ────────────────────────────────────────────────


def test_openrouter_sampling_matches_openai_shape() -> None:
    out = translate_params("openrouter", SAMPLING)
    assert out == {"temperature": 0.4, "top_p": 0.9, "max_tokens": 512}


def test_openrouter_reasoning_uses_reasoning_effort() -> None:
    out = translate_params("openrouter", REASONING)
    assert out == {"reasoning_effort": "high", "max_tokens": 512}


# ── Anthropic ─────────────────────────────────────────────────────────────────


def test_anthropic_sampling() -> None:
    out = translate_params("anthropic", SAMPLING)
    assert out == {"temperature": 0.4, "top_p": 0.9, "max_tokens": 512}


def test_anthropic_reasoning_uses_thinking_and_drops_sampling() -> None:
    """Extended thinking: send thinking={...}, bump max_tokens above budget,
    drop temperature/top_p (Anthropic pins temperature to 1 with thinking on)."""
    out = translate_params("anthropic", REASONING)
    assert out["thinking"] == {"type": "enabled", "budget_tokens": 8192}
    # max_tokens must strictly exceed the 8192 budget.
    assert out["max_tokens"] > 8192
    assert "temperature" not in out
    assert "top_p" not in out


def test_anthropic_reasoning_max_tokens_floor_when_unset() -> None:
    params = NormalizedParams(reasoning_level="low")  # budget 1024, no max_tokens
    out = translate_params("anthropic", params)
    assert out["thinking"]["budget_tokens"] == 1024
    assert out["max_tokens"] > 1024


# ── Ollama ────────────────────────────────────────────────────────────────────


def test_ollama_maps_num_ctx_and_drops_max_tokens() -> None:
    params = NormalizedParams(temperature=0.4, top_p=0.9, max_tokens=512, num_ctx=8192)
    out = translate_params("ollama", params)
    assert out == {"temperature": 0.4, "top_p": 0.9, "num_ctx": 8192}
    assert "max_tokens" not in out  # Ollama has no max_tokens kwarg


def test_ollama_drops_reasoning() -> None:
    params = NormalizedParams(reasoning_level="high", temperature=0.2)
    out = translate_params("ollama", params)
    assert out == {"temperature": 0.2}  # reasoning n/a for Ollama (§9.2)


# ── Empty + error cases ───────────────────────────────────────────────────────


def test_ollama_empty_params_yield_empty_kwargs() -> None:
    # Ollama uses num_predict (not max_tokens) and is local / not credit-metered,
    # so the default completion floor deliberately does NOT apply here.
    assert translate_params("ollama", NormalizedParams()) == {}


@pytest.mark.parametrize(
    "provider", ["openai", "openai_compatible", "azure_openai", "openrouter"]
)
def test_default_max_tokens_applied_when_unset(provider: str) -> None:
    """Regression (OpenRouter PaymentRequiredResponseError): a profile that omits
    ``max_tokens`` must still get a sane completion cap, so an unset value can't
    make the provider reserve the model's full output window."""
    out = translate_params(provider, NormalizedParams())  # type: ignore[arg-type]
    assert out == {"max_tokens": DEFAULT_MAX_TOKENS}


def test_anthropic_default_max_tokens_when_unset_non_reasoning() -> None:
    out = translate_params("anthropic", NormalizedParams())
    assert out == {"max_tokens": DEFAULT_MAX_TOKENS}


def test_explicit_max_tokens_overrides_default() -> None:
    """An explicit profile value always wins over the floor (no clobbering)."""
    out = translate_params("openrouter", NormalizedParams(max_tokens=512))
    assert out["max_tokens"] == 512


def test_unknown_provider_raises() -> None:
    with pytest.raises(UnknownProvider):
        translate_params("not-a-provider", SAMPLING)  # type: ignore[arg-type]
