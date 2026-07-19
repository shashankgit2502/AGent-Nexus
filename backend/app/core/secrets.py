"""Secret resolution (ARCHITECTURE.md §9.4).

The database stores only an ``api_key_ref`` — a *reference* to a secret, never
the secret itself. This module turns that reference into the actual key at
resolution time, and is the **only** place keys are dereferenced. Keys are never
logged, never returned to the client, and never persisted in plaintext (R5).

Reference scheme
----------------
``env:NAME``  → read ``NAME`` from the environment / a provided override map.

In production, add a ``secretsmanager://…`` (or Vault) resolver implementing the
same :class:`SecretResolver` Protocol — the resolver is injected into the model
resolver, so no caller changes. A ``None`` reference (e.g. Ollama, which needs no
key) resolves to ``None``.

Local-dev raw keys
------------------
The spec stores a *reference*, not the key (§9.4). For local development only,
:class:`EnvSecretResolver` may be constructed with ``allow_raw=True`` so a value
that is not an ``env:`` reference is treated as the literal key — this lets the
Settings UI accept a pasted API key without an env round-trip. This branch is
**gated to ``APP_ENV=local``** at the construction site and must never be enabled
in staging/production (R5: no plaintext secrets outside dev).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.core.config import Settings

_ENV_SCHEME = "env:"


class SecretNotFound(Exception):
    """A secret reference could not be resolved to a value."""

    def __init__(self, ref: str) -> None:
        # Never include the resolved value; the ref name only.
        super().__init__(f"Secret reference {ref!r} could not be resolved")
        self.ref = ref


class SecretResolver(Protocol):
    """Resolve an ``api_key_ref`` to its secret value (or ``None`` if no ref)."""

    def resolve(self, ref: str | None) -> str | None: ...


class EnvSecretResolver:
    """Resolve ``env:NAME`` references from an override map then ``os.environ``.

    The override map lets local dev feed keys from pydantic ``Settings`` without
    mutating the process environment. Unknown schemes are rejected (we never
    treat a raw string as a literal key — that would defeat the reference model).
    """

    def __init__(
        self, overrides: Mapping[str, str] | None = None, *, allow_raw: bool = False
    ) -> None:
        self._overrides = dict(overrides or {})
        self._allow_raw = allow_raw

    def resolve(self, ref: str | None) -> str | None:
        if ref is None:
            return None
        if ref.startswith(_ENV_SCHEME):
            name = ref[len(_ENV_SCHEME) :]
            value = self._overrides.get(name) or os.environ.get(name)
            if not value:
                raise SecretNotFound(ref)
            return value
        # Local-dev only (see module docstring): a non-reference value is the
        # literal key. Production constructs the resolver with allow_raw=False, so
        # an unknown scheme still fails closed.
        if self._allow_raw:
            return ref
        raise SecretNotFound(ref)


def build_secret_resolver(settings: Settings) -> EnvSecretResolver:
    """Construct the app's default secret resolver from settings.

    Seeds the ``env:`` override map with the two first-class provider keys and
    enables raw-key resolution **only** in local dev (Bug 5). This is the single
    place the local raw-key policy is decided, shared by the runtime model
    resolver (``agents.snapshot``) and the Settings validation probe.
    """
    return EnvSecretResolver(
        {
            "OPENAI_API_KEY": settings.OPENAI_API_KEY,
            "ANTHROPIC_API_KEY": settings.ANTHROPIC_API_KEY,
        },
        allow_raw=settings.is_local,
    )


class InMemorySecretResolver:
    """Map-backed resolver for unit tests: ``{ref: value}``."""

    def __init__(self, secrets: Mapping[str, str] | None = None) -> None:
        self._secrets = dict(secrets or {})

    def resolve(self, ref: str | None) -> str | None:
        if ref is None:
            return None
        try:
            return self._secrets[ref]
        except KeyError as exc:
            raise SecretNotFound(ref) from exc
