"""Agent configuration — the spawn-time inputs for one peer agent (ARCH §22.1).

``AgentConfig`` is the in-domain projection of the ``agents`` row (TECHNICAL
§11.2): persona, capability toggles, memory flag, the model selection
(profile + optional override → :class:`AgentModelRef`), and the agent's selected
skills. The Agent Factory (§22.2) consumes exactly this to build a runtime agent;
keeping it decoupled from SQLAlchemy means the factory + tests work over plain
objects and the DB impl arrives in Step 9 without touching the factory.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models_layer.resolver import AgentModelRef
from app.skills.loader import SkillSource


class Capabilities(BaseModel):
    """The agent-config capability toggles (ARCH §10.5.4 → predefined tools).

    Each enabled flag maps to one or more predefined tools assembled by the
    :class:`~app.tools.registry.ToolRegistry`. Field names are the registry's
    capability keys — they are the single source of truth for "what tools can an
    agent have", so adding a capability is a field here + a registered builder.
    """

    model_config = ConfigDict(frozen=True)

    rag: bool = False  # → search_knowledge (ARCH §10.5.2)
    web_search: bool = False  # → live web-search tool
    code_interpreter: bool = False  # → sandboxed code-exec tool
    doc_chart: bool = False  # → document/chart generation tools
    image_gen: bool = False  # → image-generation tool

    def enabled(self) -> tuple[str, ...]:
        """Return the capability keys that are toggled on, in declaration order."""
        return tuple(name for name, value in self.model_dump().items() if value)


class KnowledgeConfig(BaseModel):
    """The agent's RAG source-scoping (ARCH §10.5.3, the two screenshot toggles).

    Drives the metadata filter the ``search_knowledge`` tool applies (§10.5.2):

    * ``only_specified_sources`` — the "Only use specified sources" toggle. When
      on, retrieval is restricted to ``source_ids``; off searches the whole team +
      agent-private knowledge base.
    * ``source_ids`` — the knowledge sources the user attached to this agent.

    (The "Search all websites" toggle is a *separate* capability — live web search,
    not RAG — so it lives in :class:`Capabilities`, not here, §10.5.3.)
    """

    model_config = ConfigDict(frozen=True)

    only_specified_sources: bool = False
    source_ids: tuple[UUID, ...] = Field(default=())


class AgentConfig(BaseModel):
    """Everything needed to spawn one peer ReAct agent (§22.1)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    org_id: UUID  # top tenant (TECHNICAL §11.0); scopes knowledge/memory isolation
    team_id: UUID
    name: str
    description: str | None = None
    instructions: str = ""  # persona / system prompt body (agents.instructions)
    capabilities: Capabilities = Capabilities()
    knowledge: KnowledgeConfig = KnowledgeConfig()  # RAG source scoping (§10.5.3)
    memory_enabled: bool = False
    profile_id: UUID
    override_model_id: UUID | None = None  # ARCH Q1 model override
    skill_sources: tuple[SkillSource, ...] = Field(default=())

    def model_ref(self) -> AgentModelRef:
        """The model-selection inputs for the resolver (§9.1)."""
        return AgentModelRef(profile_id=self.profile_id, override_model_id=self.override_model_id)


class AgentRepository(Protocol):
    """Read access to agent configs, by id (repository pattern, mirrors Step 3)."""

    def get(self, agent_id: UUID) -> AgentConfig: ...

    def list_for_team(self, team_id: UUID) -> list[AgentConfig]: ...


class InMemoryAgentRepository:
    """Dict-backed repository for tests and local dev (DB impl in Step 9)."""

    def __init__(self, agents: list[AgentConfig] | None = None) -> None:
        self._by_id: dict[UUID, AgentConfig] = {a.id: a for a in (agents or [])}

    def add(self, agent: AgentConfig) -> None:
        self._by_id[agent.id] = agent

    def get(self, agent_id: UUID) -> AgentConfig:
        try:
            return self._by_id[agent_id]
        except KeyError as exc:
            raise KeyError(f"agent config {agent_id!r} not found") from exc

    def list_for_team(self, team_id: UUID) -> list[AgentConfig]:
        return [a for a in self._by_id.values() if a.team_id == team_id]
