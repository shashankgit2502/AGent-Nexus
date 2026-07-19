"""Unit tests for the predefined tool registry (ARCH §10.5.4)."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from langchain_core.tools import BaseTool, tool

from app.agents.config import AgentConfig, Capabilities
from app.tools.registry import ToolRegistry, UnknownCapability


def _agent(capabilities: Capabilities) -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name="A",
        profile_id=uuid4(),
        capabilities=capabilities,
    )


@tool
def _fake_search(query: str) -> str:
    """Fake knowledge search."""
    return f"results for {query}"


def test_assembles_tools_for_enabled_capabilities() -> None:
    registry = ToolRegistry()
    registry.register("rag", lambda cfg: [_fake_search])
    tools = registry.assemble(_agent(Capabilities(rag=True)))
    assert [t.name for t in tools] == ["_fake_search"]
    assert all(isinstance(t, BaseTool) for t in tools)


def test_disabled_capabilities_contribute_no_tools() -> None:
    registry = ToolRegistry()
    registry.register("rag", lambda cfg: [_fake_search])
    assert registry.assemble(_agent(Capabilities(rag=False))) == []


def test_enabled_capability_without_builder_is_skipped_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No builder registered for web_search → skipped (not crashed), and logged so
    # the gap is visible (it isn't an error: the backing tool just isn't wired yet).
    registry = ToolRegistry()
    with caplog.at_level(logging.WARNING):
        tools = registry.assemble(_agent(Capabilities(web_search=True)))
    assert tools == []
    assert "web_search" in caplog.text


def test_registering_unknown_capability_raises() -> None:
    registry = ToolRegistry()
    with pytest.raises(UnknownCapability):
        registry.register("telepathy", lambda cfg: [])
