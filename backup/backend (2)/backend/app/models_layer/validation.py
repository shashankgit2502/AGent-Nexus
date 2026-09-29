"""Connection validation: SSRF guard + validation probe (ARCH §9.4 / §27.3).

Two security-blocking concerns from the spec live here:

1. **SSRF guard (§9.4).** A user-supplied ``base_url`` (Ollama / OpenAI-compatible
   / Azure) is an SSRF vector: a malicious URL could make our server fetch an
   internal address (cloud metadata endpoints, internal services). Before a
   connection is usable we validate the scheme and, unless private addresses are
   explicitly allowed (local Ollama dev), reject hosts that resolve to
   loopback/private/link-local/reserved IP ranges.

2. **Validation probe (§27.3).** A cheap call (a 1-token completion) on save
   catches bad keys, wrong base URLs, and — for pass-through providers like
   OpenRouter — wrong model identifiers that would otherwise only 404 mid-session.
   The probe is structured so the model call is injected, keeping it unit-testable
   without network access.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from langchain_core.language_models.chat_models import BaseChatModel

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class SSRFBlocked(Exception):
    """A ``base_url`` failed the SSRF allowlist check and must not be used."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"base_url {url!r} blocked: {reason}")
        self.url = url
        self.reason = reason


def validate_base_url(url: str, *, allow_private: bool = False) -> None:
    """Validate a user-supplied ``base_url`` against the SSRF allowlist.

    Args:
        url: the base URL to validate.
        allow_private: permit loopback/private hosts (true only for trusted local
            providers such as a developer's Ollama at ``http://localhost:11434``).

    Raises:
        SSRFBlocked: if the scheme is not http(s), the host is missing, or — when
            ``allow_private`` is false — the host resolves to a non-public IP.
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFBlocked(url, f"scheme {parsed.scheme!r} not in {sorted(_ALLOWED_SCHEMES)}")
    host = parsed.hostname
    if not host:
        raise SSRFBlocked(url, "missing host")
    if allow_private:
        return
    for info in _resolve(url, host):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            raise SSRFBlocked(url, f"host resolves to non-public address {ip}")


def _resolve(url: str, host: str) -> list[Any]:
    """Resolve ``host`` to ``getaddrinfo`` records; a failure is itself blocking."""
    try:
        return socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFBlocked(url, f"host did not resolve ({exc})") from exc


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a validation probe; ``ok`` gates marking a connection validated."""

    ok: bool
    detail: str


def probe_model(model: BaseChatModel, *, prompt: str = "ping") -> ProbeResult:
    """Run a minimal completion to confirm a model is reachable and authorized.

    Any provider error (bad key, wrong base_url, unknown model id) is captured
    and surfaced as ``ok=False`` with the message — we do **not** swallow it
    silently (R3). The exception is intentionally broad here because providers
    raise heterogeneous error types; the message is preserved for diagnosis.
    """
    try:
        model.invoke(prompt)
    except Exception as exc:  # noqa: BLE001 — probe must report any provider error
        return ProbeResult(ok=False, detail=f"{type(exc).__name__}: {exc}")
    return ProbeResult(ok=True, detail="reachable")
