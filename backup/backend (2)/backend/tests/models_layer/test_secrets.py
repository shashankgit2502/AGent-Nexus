"""Tests for secret resolution (ARCH §9.4)."""

from __future__ import annotations

import pytest

from app.core.secrets import EnvSecretResolver, InMemorySecretResolver, SecretNotFound


def test_none_ref_resolves_to_none() -> None:
    # Ollama and other key-less providers carry a None api_key_ref.
    assert EnvSecretResolver().resolve(None) is None
    assert InMemorySecretResolver().resolve(None) is None


def test_env_scheme_reads_from_overrides_first() -> None:
    resolver = EnvSecretResolver({"OPENAI_API_KEY": "from-settings"})
    assert resolver.resolve("env:OPENAI_API_KEY") == "from-settings"


def test_env_scheme_falls_back_to_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_KEY", "from-environ")
    assert EnvSecretResolver().resolve("env:MY_KEY") == "from-environ"


def test_missing_env_secret_raises() -> None:
    with pytest.raises(SecretNotFound):
        EnvSecretResolver().resolve("env:DEFINITELY_NOT_SET_12345")


def test_non_env_scheme_is_rejected_not_treated_as_literal() -> None:
    # A raw string must never be used as a literal key (defeats the ref model).
    with pytest.raises(SecretNotFound):
        EnvSecretResolver().resolve("sk-literal-key")


def test_allow_raw_treats_non_reference_as_literal_key() -> None:
    # Local-dev only (Bug 5): a pasted raw key resolves to itself.
    resolver = EnvSecretResolver(allow_raw=True)
    assert resolver.resolve("sk-or-v1-abc123") == "sk-or-v1-abc123"


def test_allow_raw_still_prefers_env_scheme() -> None:
    # env: references keep resolving from overrides even when raw is allowed.
    resolver = EnvSecretResolver({"OPENAI_API_KEY": "from-settings"}, allow_raw=True)
    assert resolver.resolve("env:OPENAI_API_KEY") == "from-settings"


def test_allow_raw_none_still_resolves_to_none() -> None:
    assert EnvSecretResolver(allow_raw=True).resolve(None) is None


def test_in_memory_resolver_maps_refs() -> None:
    resolver = InMemorySecretResolver({"secret://openai": "abc"})
    assert resolver.resolve("secret://openai") == "abc"
    with pytest.raises(SecretNotFound):
        resolver.resolve("secret://missing")
