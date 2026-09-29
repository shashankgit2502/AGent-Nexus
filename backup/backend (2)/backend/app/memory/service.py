"""Long-term memory read/write service (ARCHITECTURE.md §10 / §25).

A thin, typed facade over the **same** backend composition (``CompositeBackend`` →
``StoreBackend`` at ``/memories/``) an agent uses for its memory files (§10.1).
Using the real backend — not a re-implemented store accessor (R2) — guarantees one
view of memory: what an agent persists in a run, this service reads back, and
vice-versa. It backs two things:

* **Cross-session recall** — a memory written in one run is mounted into the
  agent's prompt on the next build (the Step-7 "an agent recalls a prior-session
  memory" acceptance), because both go through the same namespaced store.
* **The Memory Explorer API (§14, Step 9)** — reading an agent's private memory
  and the team-shared layer (§25.1).

Namespacing is delegated to :mod:`app.memory.namespaces` so the per-agent
(`("team", t, "agent", a)`) and team-shared (`("team", t, "shared")`) boundaries
match §25.1 exactly. The team-shared layer is exposed **read-only** here: agents
must not pollute shared policies (§25.1).
"""

from __future__ import annotations

from uuid import UUID

from deepagents.backends import (
    BackendProtocol,
    CompositeBackend,
    StateBackend,
    StoreBackend,
)
from langgraph.store.base import BaseStore

from app.memory.namespaces import (
    AGENTS_MEMORY_FILE,
    MEMORY_ROOT,
    NamespaceFactory,
    agent_memory_namespace,
    team_shared_namespace,
)


class MemoryWriteError(RuntimeError):
    """A memory write failed. Surfaced (not swallowed, R3) with the backend reason."""


def _static_namespace(namespace: tuple[str, ...]) -> NamespaceFactory:
    """Wrap a fixed namespace tuple as the runtime-ignoring factory StoreBackend wants."""

    def _factory(_runtime: object) -> tuple[str, ...]:
        return namespace

    return _factory


def build_memory_backend(store: BaseStore, namespace: tuple[str, ...]) -> BackendProtocol:
    """Build the memory backend exactly as the agent factory mounts it (§10.1).

    Both the agent and this service must address memory by its **logical** path
    (``/memories/AGENTS.md``). The factory mounts the persistent ``StoreBackend``
    behind a ``CompositeBackend`` route at :data:`MEMORY_ROOT`, and that route
    **strips its prefix** before delegating — so the physical store key is
    ``/AGENTS.md``, not ``/memories/AGENTS.md``. If this service wrote through a
    *standalone* ``StoreBackend`` it would key the file at ``/memories/AGENTS.md``
    and the agent would never find it. Mirroring the same composite here guarantees
    both sides apply the identical path translation, so a memory written by one is
    read by the other (this is the root-cause fix for cross-session recall).

    The ``StateBackend`` default is never exercised — we only ever touch the
    ``/memories/`` route — but it matches the factory's composition shape.
    """
    return CompositeBackend(
        default=StateBackend(),
        routes={MEMORY_ROOT: StoreBackend(store=store, namespace=_static_namespace(namespace))},
    )


class MemoryService:
    """Read/write agents' long-term memory via the same backend composition (§10.1).

    Args:
        store: the LangGraph ``Store`` (``PostgresStore`` in prod; ``InMemoryStore``
            in tests). The same store instance the agent factory mounts, so writes
            here are visible to a later-built agent and vice-versa.
    """

    def __init__(self, store: BaseStore) -> None:
        self._store = store

    def _backend(self, namespace: tuple[str, ...]) -> BackendProtocol:
        return build_memory_backend(self._store, namespace)

    def write(
        self,
        *,
        org_id: UUID,
        team_id: UUID,
        agent_id: UUID,
        content: str,
        path: str = AGENTS_MEMORY_FILE,
    ) -> None:
        """Persist ``content`` to an agent's private memory file (§25.1).

        Raises:
            MemoryWriteError: the backend reported a write failure.
        """
        namespace = agent_memory_namespace(org_id, team_id, agent_id)
        result = self._backend(namespace).write(path, content)
        if result.error:
            raise MemoryWriteError(result.error)

    def upsert(
        self,
        *,
        org_id: UUID,
        team_id: UUID,
        agent_id: UUID,
        content: str,
        path: str = AGENTS_MEMORY_FILE,
    ) -> None:
        """Create-or-overwrite an agent's memory file (the recall-rollup refresh path).

        ``write`` is **create-only** — ``StoreBackend.write`` refuses to clobber an
        existing path. The post-run consolidation step regenerates the
        ``/memories/AGENTS.md`` rollup from the agent's records on every run, so it
        needs overwrite semantics. ``upload_files`` provides exactly that: it routes
        through the same ``CompositeBackend`` (so the key translation matches
        :meth:`read` and the agent's own recall — no key drift, see
        :func:`build_memory_backend`) and persists via an unconditional
        ``store.put``. This is why the rollup goes through ``upload_files`` rather
        than ``write`` + a delete dance.

        Raises:
            MemoryWriteError: the backend reported a write failure.
        """
        backend = self._backend(agent_memory_namespace(org_id, team_id, agent_id))
        responses = backend.upload_files([(path, content.encode("utf-8"))])
        error = responses[0].error if responses else "no upload response"
        if error:
            raise MemoryWriteError(error)

    def read(
        self, *, org_id: UUID, team_id: UUID, agent_id: UUID, path: str = AGENTS_MEMORY_FILE
    ) -> str | None:
        """Return an agent's private memory file content, or ``None`` if absent.

        A missing file is a normal "no memory yet" state, returned as ``None`` — it
        is not an error, so it is not raised (this is the recall read path).
        """
        result = self._backend(agent_memory_namespace(org_id, team_id, agent_id)).read(path)
        if result.error or result.file_data is None:
            return None
        return result.file_data["content"]

    def read_shared(
        self, *, org_id: UUID, team_id: UUID, path: str = AGENTS_MEMORY_FILE
    ) -> str | None:
        """Return team-shared memory content, or ``None`` if absent (read-only, §25.1)."""
        result = self._backend(team_shared_namespace(org_id, team_id)).read(path)
        if result.error or result.file_data is None:
            return None
        return result.file_data["content"]
