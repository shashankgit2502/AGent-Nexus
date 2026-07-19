"""Provider model discovery + connection validation probe (ARCH §27.2 / §27.3).

A single network call lists a provider's model identifiers. It serves two
purposes:

* **Discovery (§27.2):** populate the model catalog with the ids a connection
  exposes (``GET /v1/models``, Ollama ``/api/tags``, Azure ``/openai/deployments``).
* **Validation probe (§27.3):** a successful list call confirms the key/base_url
  are usable, so we mark the connection ``validated``. For pass-through providers
  (OpenRouter) the list is public, so a success there proves reachability rather
  than key validity — we report counts honestly and never overclaim.

Design notes
------------
* **SSRF guard (§9.4):** any user-supplied ``base_url`` is validated against the
  allowlist before we make the request (loopback/private hosts permitted only when
  ``allow_private`` — local Ollama dev).
* **Testability:** the ``httpx.AsyncClient`` is injectable so unit tests drive the
  parser/headers/URL logic without network access (R5).
* **No swallowing (R3):** any failure is captured and surfaced in
  :class:`DiscoveryResult.detail`; it is never silently ignored.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from app.models_layer.base_url import canonical_base_url
from app.models_layer.validation import SSRFBlocked, validate_base_url

logger = logging.getLogger(__name__)

# Provider default base URLs (used when a connection sets no base_url).
_DEFAULT_BASE: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "anthropic": "https://api.anthropic.com/v1",
}
_ANTHROPIC_VERSION = "2023-06-01"
_AZURE_DEFAULT_API_VERSION = "2024-02-01"
_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class DiscoveredModel:
    """One model the provider exposes, with the capability flags it advertises.

    The §9.3 hard gate (``supports_tools``) is the load-bearing one: it decides
    whether a mesh agent may resolve this model. OpenAI-shaped providers that ship
    capabilities inline (OpenRouter via ``supported_parameters`` + ``architecture``)
    populate these honestly; providers whose ``/models`` lists only ids (plain
    OpenAI, Ollama ``/api/tags``) fall back to the conservative defaults below, and
    the user refines them in the catalog (models.dev enrichment is still deferred
    for those, ARCH §27.2).
    """

    id: str
    supports_tools: bool = False
    supports_vision: bool = False
    supports_reasoning: bool = False
    context_window: int | None = None
    model_type: str = "chat"  # 'chat' | 'embedding'; classified from the id (Approach B)


def classify_model_type(model_id: str) -> str:
    """Best-effort chat-vs-embedding classification from a model id (Approach B).

    Providers' ``/models`` listings almost never tag a model's *type*, so discovery
    can't read it the way it reads ``supports_tools``. The pragmatic signal is the id
    itself: embedding models are conventionally named with ``embed`` (``nemotron:embed``,
    ``text-embedding-3-small``, ``bge-embedding``). This is a heuristic, not a
    guarantee — it only sets the *initial* type on a newly-discovered row; the user
    corrects any miss via ``PATCH /providers/catalog/{id}``. We deliberately do not
    overwrite the type on re-discover, so a manual reclassification sticks.
    """
    return "embedding" if "embed" in model_id.lower() else "chat"


@dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of a discovery/probe call.

    ``ok`` gates marking a connection validated; ``models`` feeds catalog
    population (with capabilities); ``detail`` is a human-readable message (model
    count or error).
    """

    ok: bool
    models: list[DiscoveredModel]
    detail: str

    @property
    def model_ids(self) -> list[str]:
        """The bare model identifiers (back-compat with id-only callers/tests)."""
        return [m.id for m in self.models]


def _models_url(provider: str, base_url: str | None) -> str:
    """Resolve the model-list URL, tolerating a pasted chat/completions path."""
    # canonical_base_url strips a pasted ".../chat/completions" back to the root.
    base = (canonical_base_url(base_url) or _DEFAULT_BASE.get(provider, "")).rstrip("/")
    if provider == "ollama":
        return f"{base}/api/tags"
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def _headers(provider: str, api_key: str | None, api_version: str | None) -> dict[str, str]:
    """Build provider-appropriate auth headers."""
    if provider == "anthropic":
        headers = {"anthropic-version": api_version or _ANTHROPIC_VERSION}
        if api_key:
            headers["x-api-key"] = api_key
        return headers
    if provider == "azure_openai":
        return {"api-key": api_key} if api_key else {}
    # openai / openai_compatible / openrouter use Bearer auth.
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _coerce_context_window(row: Mapping[str, Any]) -> int | None:
    """Best-effort context-window from the common field spellings."""
    raw = row.get("context_length") or row.get("context_window")
    top = row.get("top_provider")
    if raw is None and isinstance(top, Mapping):
        raw = top.get("context_length")
    return int(raw) if isinstance(raw, (int, float)) else None


def _model_from_row(mid: str, row: Mapping[str, Any]) -> DiscoveredModel:
    """Map one OpenAI-shaped catalog row to a capability-bearing model.

    Capability signals (OpenRouter, verified against ``/api/v1/models``):
    * ``supported_parameters`` — an array; presence of ``"tools"`` means the model
      accepts tool definitions (the §9.3 gate). ``"reasoning"`` marks reasoning.
    * ``architecture.input_modalities`` — contains ``"image"`` for vision models.
    Missing fields → conservative ``False`` defaults (provider lists ids only).
    """
    sp = row.get("supported_parameters")
    params = {str(p) for p in sp} if isinstance(sp, list) else set()
    arch = row.get("architecture")
    modalities = arch.get("input_modalities") if isinstance(arch, Mapping) else None
    if isinstance(modalities, str):
        modalities = [modalities]
    mod_set = {str(m).lower() for m in modalities} if isinstance(modalities, list) else set()
    return DiscoveredModel(
        id=mid,
        supports_tools="tools" in params or "tool_choice" in params,
        supports_vision="image" in mod_set,
        supports_reasoning="reasoning" in params or "include_reasoning" in params,
        context_window=_coerce_context_window(row),
        model_type=classify_model_type(mid),
    )


def _parse_models(provider: str, payload: dict[str, Any]) -> list[DiscoveredModel]:
    """Extract models (id + advertised capabilities) from a list response."""
    if provider == "ollama":
        # /api/tags lists names only — no capability metadata to read, but the id
        # still classifies chat vs embedding (Approach B).
        return [
            DiscoveredModel(id=m["name"], model_type=classify_model_type(m["name"]))
            for m in payload.get("models", [])
            if isinstance(m, dict) and "name" in m
        ]
    # OpenAI-shaped: {"data": [{"id": ..., "supported_parameters": [...]}]}.
    rows = payload.get("data") or payload.get("models") or []
    out: list[DiscoveredModel] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mid = row.get("id") or row.get("name")
        if mid:
            out.append(_model_from_row(str(mid), row))
    return out


async def discover_models(
    *,
    provider: str,
    base_url: str | None,
    api_key: str | None,
    api_version: str | None = None,
    allow_private: bool = False,
    client: httpx.AsyncClient | None = None,
) -> DiscoveryResult:
    """List a provider's model ids; success doubles as the validation probe.

    Args:
        provider: the connection provider enum value.
        base_url: connection base_url (None → provider default).
        api_key: the resolved API key (already dereferenced from api_key_ref).
        api_version: Azure/Anthropic API version override.
        allow_private: permit loopback/private hosts (local Ollama only).
        client: injected httpx client (tests); a default one is created otherwise.

    Returns:
        DiscoveryResult with ok/model_ids/detail. Never raises for provider or
        network errors — those are reported via ``ok=False`` + ``detail`` (R3).
    """
    if base_url:
        try:
            validate_base_url(base_url, allow_private=allow_private)
        except SSRFBlocked as exc:
            return DiscoveryResult(ok=False, models=[], detail=f"SSRFBlocked: {exc}")

    if provider == "azure_openai":
        base = (base_url or "").rstrip("/")
        if not base:
            return DiscoveryResult(
                ok=False, models=[], detail="azure_openai requires a base_url"
            )
        version = api_version or _AZURE_DEFAULT_API_VERSION
        url = f"{base}/openai/deployments?api-version={version}"
    else:
        url = _models_url(provider, base_url)

    headers = _headers(provider, api_key, api_version)
    owns_client = client is None
    active = client or httpx.AsyncClient(timeout=_TIMEOUT_S)
    try:
        resp = await active.get(url, headers=headers)
        resp.raise_for_status()
        models = _parse_models(provider, resp.json())
        tool_count = sum(1 for m in models if m.supports_tools)
        detail = f"{len(models)} models reachable ({tool_count} tool-capable)"
        return DiscoveryResult(ok=True, models=models, detail=detail)
    except Exception as exc:  # noqa: BLE001 — surface any provider/network error
        logger.info("model discovery failed for provider=%s url=%s: %s", provider, url, exc)
        return DiscoveryResult(ok=False, models=[], detail=f"{type(exc).__name__}: {exc}")
    finally:
        if owns_client:
            await active.aclose()
