"""Canonicalize a provider ``base_url`` to the API root (Bug 5 follow-up).

OpenAI-compatible clients (used for ``openai``/``openrouter``/``openai_compatible``)
expect ``base_url`` to be the API *root* (e.g. ``https://openrouter.ai/api/v1``)
and append ``/chat/completions`` themselves. Users routinely paste the full chat
endpoint instead, which makes the client request ``…/chat/completions/chat/completions``
→ 404 at inference time (the model "works" in discovery but chat silently stubs).

This single helper strips that trailing operation path so both the resolver
(``init_chat_model``) and discovery use the API root. It is intentionally
conservative: it only removes the two completion suffixes and a trailing slash.
"""

from __future__ import annotations

_OPERATION_SUFFIXES = ("/chat/completions", "/completions")


def canonical_base_url(base_url: str | None) -> str | None:
    """Return ``base_url`` reduced to the API root (or ``None`` if empty).

    Idempotent: a URL already at the API root is returned unchanged (minus any
    trailing slash).
    """
    if not base_url:
        return base_url
    url = base_url.strip().rstrip("/")
    for suffix in _OPERATION_SUFFIXES:
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    return url or None
