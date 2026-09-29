"""Tests for base_url canonicalization (Bug 5 follow-up)."""

from __future__ import annotations

import pytest

from app.models_layer.base_url import canonical_base_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The reported repro: a pasted chat endpoint reduces to the API root.
        ("https://openrouter.ai/api/v1/chat/completions", "https://openrouter.ai/api/v1"),
        ("https://openrouter.ai/api/v1/completions", "https://openrouter.ai/api/v1"),
        # Already canonical → unchanged (idempotent), trailing slash removed.
        ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1"),
        ("https://openrouter.ai/api/v1/", "https://openrouter.ai/api/v1"),
        ("http://localhost:11434", "http://localhost:11434"),
        # Empty / None pass through.
        (None, None),
        ("", ""),
    ],
)
def test_canonical_base_url(raw: str | None, expected: str | None) -> None:
    assert canonical_base_url(raw) == expected


def test_canonical_base_url_is_idempotent() -> None:
    once = canonical_base_url("https://openrouter.ai/api/v1/chat/completions")
    assert canonical_base_url(once) == once
