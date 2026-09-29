"""Long-term memory namespaces (ARCHITECTURE.md §10 / §25.1).

Each agent's private cross-session memory is isolated under a per-(org, team, agent)
namespace in the LangGraph ``Store``. `deepagents`' ``StoreBackend`` accepts a
*namespace factory* — a callable invoked with the tool runtime that returns the
namespace tuple — so memory writes/reads are automatically scoped to the right
agent. This module owns that namespace shape so it stays consistent with §25.1
and is set in one place.

**Org-prefixed (Item 3 decision).** Organization is the top tenant (TECHNICAL §11.0),
so the namespace leads with ``("org", org_id, …)`` for defence-in-depth store-level
tenant isolation — matching the relational ``org_id`` scoping + RLS. This supersedes
the earlier team-first shape; ARCHITECTURE §10/§25.1 are updated to match.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

# §25.1: ("org", org_id, "team", team_id, "agent", agent_id) — private agent memory.
NamespaceFactory = Callable[[Any], tuple[str, ...]]

# Where deepagents' MemoryMiddleware loads/saves long-term memory. The agent reads
# and writes these paths through the standard filesystem tools; the StoreBackend
# route at MEMORY_ROOT persists them cross-session (§10.1). Owned here so the
# factory and the MemoryService agree on one path.
MEMORY_ROOT = "/memories/"
AGENTS_MEMORY_FILE = "/memories/AGENTS.md"


def agent_memory_namespace(org_id: UUID, team_id: UUID, agent_id: UUID) -> tuple[str, ...]:
    """Return the private long-term memory namespace for one agent (§25.1)."""
    return ("org", str(org_id), "team", str(team_id), "agent", str(agent_id))


def agent_memory_items_namespace(
    org_id: UUID, team_id: UUID, agent_id: UUID
) -> tuple[str, ...]:
    """Return the namespace for an agent's structured memory **records** (§14/§25.1).

    A *sub-namespace* of the private agent namespace (an extra ``"memories"``
    component) that holds the Memory Explorer's per-item records — one LangGraph
    ``Store`` key per memory (fact / experience / session-learning / summary), each
    carrying its own metadata (kind, pinned, created_at, run_id). It is kept
    deliberately distinct from :func:`agent_memory_namespace`, where deepagents'
    ``MemoryMiddleware`` mounts the single ``/memories/AGENTS.md`` recall file: if
    the records shared that namespace, the agent's ``ls /memories/`` would list every
    record as a phantom file. Same ``(org, team, agent)`` isolation as §25.1, one
    level deeper.
    """
    return ("org", str(org_id), "team", str(team_id), "agent", str(agent_id), "memories")


def team_shared_namespace(org_id: UUID, team_id: UUID) -> tuple[str, ...]:
    """Return the team-shared memory namespace (§25.1).

    Holds team policies/notes and endorsed memories. Read-only to agents (writes
    go through admins / an endorsement flow, §25.1); the MemoryService exposes it
    read-only so a misconfigured agent cannot pollute the shared layer.
    """
    return ("org", str(org_id), "team", str(team_id), "shared")


def make_namespace_factory(org_id: UUID, team_id: UUID, agent_id: UUID) -> NamespaceFactory:
    """Build the namespace factory ``StoreBackend`` expects.

    The returned callable ignores the runtime argument (our namespace depends only
    on the static org/team/agent identity), but matches the ``StoreBackend(namespace=)``
    signature verified against deepagents 0.6.10.
    """
    namespace = agent_memory_namespace(org_id, team_id, agent_id)

    def _factory(_runtime: Any) -> tuple[str, ...]:
        return namespace

    return _factory
