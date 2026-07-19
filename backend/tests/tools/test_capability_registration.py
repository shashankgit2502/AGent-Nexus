"""Capability → tool assembly for the settings-driven tools (Bug 5 Part A).

Proves an agent that enables ``web_search`` / ``code_interpreter`` actually receives
those tools once they are registered the way ``build_mesh_context`` registers them —
closing the gap where those capabilities were declared but never built.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.agents.config import AgentConfig, Capabilities
from app.tools.code_interpreter import make_code_interpreter_tool
from app.tools.registry import ToolRegistry
from app.tools.web_search import make_web_search_tool


@dataclass
class _Settings:
    WEB_SEARCH_API_KEY: str = ""
    WEB_SEARCH_MAX_RESULTS: int = 5
    CODE_INTERPRETER_ENABLED: bool = False
    CODE_INTERPRETER_TIMEOUT_S: float = 10.0


def test_web_search_and_code_interpreter_assemble_for_an_agent() -> None:
    settings = _Settings()
    registry = ToolRegistry()
    web = make_web_search_tool(settings)  # type: ignore[arg-type]
    code = make_code_interpreter_tool(settings)  # type: ignore[arg-type]
    registry.register("web_search", lambda _cfg: [web])
    registry.register("code_interpreter", lambda _cfg: [code])

    cfg = AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name="Analyst",
        profile_id=uuid4(),
        capabilities=Capabilities(web_search=True, code_interpreter=True),
    )
    names = {t.name for t in registry.assemble(cfg)}
    assert names == {"web_search", "code_interpreter"}

    # An agent that enables neither gets neither.
    plain = cfg.model_copy(update={"capabilities": Capabilities()})
    assert registry.assemble(plain) == []
