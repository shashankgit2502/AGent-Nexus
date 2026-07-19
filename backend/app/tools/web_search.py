"""The ``web_search`` capability tool — live web search via Tavily (ARCH §10.5.4).

What the **web_search capability** adds to an agent: a tool that queries the public
web and returns ranked snippets the agent can ground its answer in. Real search
requires a Tavily key (``WEB_SEARCH_API_KEY``); without one the tool is still present
and callable but returns an honest "not configured" message — so a misconfigured
deployment is visible (the agent reports it) rather than silently doing nothing
(R3 — no silent fakery).

Primitive choice (R1/R2): Tavily's documented REST endpoint
(``POST https://api.tavily.com/search``, verified via Context7) called with the
already-vendored ``httpx.AsyncClient`` (the same injectable-for-tests pattern as
:mod:`app.models_layer.discovery`) — no extra SDK dependency. The tool is **async**
because the mesh runs agents asynchronously; a failed call returns its reason as the
tool observation (the agent reacts to it) instead of crashing the round.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import httpx
from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)

_TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT_S = 20.0
_NOT_CONFIGURED = (
    "web_search is not configured (no WEB_SEARCH_API_KEY set), so live web results "
    "are unavailable. Answer from your own knowledge and say results may be dated."
)


def _format_results(results: Sequence[dict[str, Any]]) -> str:
    """Render Tavily results as source-attributed snippets for the agent."""
    if not results:
        return "No web results found."
    lines: list[str] = []
    for r in results:
        title = r.get("title") or "(untitled)"
        url = r.get("url") or ""
        content = (r.get("content") or "").strip()
        lines.append(f"[{title}]({url})\n{content}")
    return "\n\n".join(lines)


async def tavily_search(
    query: str,
    *,
    api_key: str,
    max_results: int,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Call Tavily's ``/search`` and return the raw ``results`` list (R1-verified).

    ``client`` is injectable so unit tests drive the call without network (mirrors
    :mod:`app.models_layer.discovery`); production creates a short-lived client.
    """
    payload = {"query": query, "max_results": max_results, "search_depth": "basic"}
    headers = {"Authorization": f"Bearer {api_key}"}
    active = client or httpx.AsyncClient(timeout=_TIMEOUT_S)
    try:
        response = await active.post(_TAVILY_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    finally:
        if client is None:
            await active.aclose()
    results = data.get("results", [])
    return results if isinstance(results, list) else []


def make_web_search_tool(
    settings: Any, *, client: httpx.AsyncClient | None = None
) -> BaseTool:
    """Build the ``web_search`` tool from settings (real when a key is configured)."""
    api_key = (settings.WEB_SEARCH_API_KEY or "").strip()
    max_results = int(settings.WEB_SEARCH_MAX_RESULTS)

    @tool
    async def web_search(query: str) -> str:
        """Search the public web for current information and return ranked snippets."""
        if not api_key:
            return _NOT_CONFIGURED
        try:
            results = await tavily_search(
                query, api_key=api_key, max_results=max_results, client=client
            )
        except Exception as exc:  # noqa: BLE001 — surface to the agent as an observation.
            # A search failure is the agent's to handle (retry / answer without it),
            # not a reason to crash the round; logged with context, returned as text.
            logger.warning("web_search failed: %s: %s", type(exc).__name__, exc)
            return f"web_search failed ({type(exc).__name__}): {exc}"
        return _format_results(results)

    return web_search
