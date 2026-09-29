"""MemoryService tests (ARCH §10 / §25.1).

Round-trip, per-agent isolation, and the read-only team-shared layer, all over the
real ``StoreBackend`` (R2) on a ``langgraph.store.memory.InMemoryStore``. Namespaces
are org-prefixed (Item 3 decision, §25.1), so every call carries ``org_id``.
"""

from __future__ import annotations

from uuid import uuid4

from langgraph.store.memory import InMemoryStore

from app.memory.namespaces import AGENTS_MEMORY_FILE, team_shared_namespace
from app.memory.service import MemoryService, build_memory_backend


def test_write_then_read_roundtrips() -> None:
    svc = MemoryService(InMemoryStore())
    org, team, agent = uuid4(), uuid4(), uuid4()
    svc.write(org_id=org, team_id=team, agent_id=agent, content="prefers pgvector")
    assert svc.read(org_id=org, team_id=team, agent_id=agent) == "prefers pgvector"


def test_read_absent_returns_none_not_error() -> None:
    svc = MemoryService(InMemoryStore())
    assert svc.read(org_id=uuid4(), team_id=uuid4(), agent_id=uuid4()) is None


def test_memory_is_isolated_per_agent() -> None:
    store = InMemoryStore()
    svc = MemoryService(store)
    org, team, agent_1, agent_2 = uuid4(), uuid4(), uuid4(), uuid4()
    svc.write(org_id=org, team_id=team, agent_id=agent_1, content="agent-1 only")
    assert svc.read(org_id=org, team_id=team, agent_id=agent_2) is None
    assert svc.read(org_id=org, team_id=team, agent_id=agent_1) == "agent-1 only"


def test_read_shared_layer() -> None:
    store = InMemoryStore()
    svc = MemoryService(store)
    org, team = uuid4(), uuid4()
    # Seed the shared namespace the way an admin/endorsement flow would (§25.1),
    # via the same backend composition the service reads through (no key drift).
    build_memory_backend(store, team_shared_namespace(org, team)).write(
        AGENTS_MEMORY_FILE, "team policy: cite sources"
    )

    assert svc.read_shared(org_id=org, team_id=team) == "team policy: cite sources"
    # The shared layer is distinct from any agent's private namespace.
    assert svc.read(org_id=org, team_id=team, agent_id=uuid4()) is None
