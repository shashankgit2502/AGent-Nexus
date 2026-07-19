"""web_search capability tool tests (Bug 5 Part A, ARCH §10.5.4).

The tool is real when ``WEB_SEARCH_API_KEY`` is set (Tavily REST via httpx) and an
honest "not configured" message otherwise. We drive the HTTP boundary with an
injected fake ``httpx.AsyncClient`` so no network is touched (mirrors the discovery
probe's test pattern).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.tools.web_search import make_web_search_tool, tavily_search


@dataclass
class _Settings:
    WEB_SEARCH_API_KEY: str = ""
    WEB_SEARCH_MAX_RESULTS: int = 5


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict[str, Any]:
        return self._payload


class _RecordingClient:
    """Captures the request and returns a canned response (stands in for httpx)."""

    def __init__(self, payload: dict[str, Any], *, boom: bool = False) -> None:
        self._payload = payload
        self._boom = boom
        self.posted: dict[str, Any] | None = None

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]):  # noqa: ANN001,A002
        if self._boom:
            raise httpx.ConnectError("network down")
        self.posted = {"url": url, "json": json, "headers": headers}
        return _FakeResponse(self._payload)


async def test_tavily_search_sends_query_and_parses_results() -> None:
    client = _RecordingClient(
        {"results": [{"title": "T", "url": "http://x", "content": "snippet", "score": 0.9}]}
    )
    results = await tavily_search("pgvector", api_key="tvly-k", max_results=3, client=client)  # type: ignore[arg-type]

    assert client.posted is not None
    assert client.posted["url"].endswith("/search")
    assert client.posted["json"] == {"query": "pgvector", "max_results": 3, "search_depth": "basic"}
    assert client.posted["headers"]["Authorization"] == "Bearer tvly-k"
    assert results[0]["url"] == "http://x"


async def test_tool_without_key_is_present_but_honest() -> None:
    tool = make_web_search_tool(_Settings(WEB_SEARCH_API_KEY=""))
    assert tool.name == "web_search"
    out = await tool.ainvoke({"query": "anything"})
    assert "not configured" in out


async def test_tool_with_key_formats_results() -> None:
    client = _RecordingClient(
        {"results": [{"title": "Messi", "url": "http://w", "content": "footballer"}]}
    )
    tool = make_web_search_tool(_Settings(WEB_SEARCH_API_KEY="tvly-k"), client=client)  # type: ignore[arg-type]
    out = await tool.ainvoke({"query": "who is messi"})
    assert "Messi" in out and "http://w" in out and "footballer" in out


async def test_tool_returns_failure_as_observation_not_crash() -> None:
    client = _RecordingClient({}, boom=True)
    tool = make_web_search_tool(_Settings(WEB_SEARCH_API_KEY="tvly-k"), client=client)  # type: ignore[arg-type]
    out = await tool.ainvoke({"query": "q"})
    assert "web_search failed" in out  # surfaced to the agent, not raised


async def test_tool_reports_no_results_cleanly() -> None:
    tool = make_web_search_tool(
        _Settings(WEB_SEARCH_API_KEY="tvly-k"), client=_RecordingClient({"results": []})  # type: ignore[arg-type]
    )
    assert "No web results" in await tool.ainvoke({"query": "q"})
