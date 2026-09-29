"""Structured long-term memory **records** for the Memory Explorer (ARCH §14 / §25.1).

Where :mod:`app.memory.service` exposes the single ``/memories/AGENTS.md`` file that
deepagents loads into an agent's prompt for recall (§10.1), this module is the
*Explorer* data layer: one LangGraph ``Store`` key per memory, each carrying its own
metadata so the UI can **list, search, delete, and pin** individual memories
(FRONTEND_SPEC §14, ARCH §14).

Why the raw ``BaseStore`` and not deepagents' ``StoreBackend`` (R2, deliberate):
``StoreBackend`` has *file* semantics — it wraps content in ``FileData`` and refuses
to overwrite an existing path — which is wrong for mutable records whose ``pinned``
flag toggles. ``BaseStore`` (``put``/``get``/``search``/``delete``) is the right
LangGraph primitive for record CRUD and is itself a real framework primitive, so
this is not a re-implementation — it is the correct one for this shape.

Records live in :func:`~app.memory.namespaces.agent_memory_items_namespace`, a
sub-namespace of the private agent namespace, so they never appear in the agent's
``ls /memories/`` file view.

Ordering & search (M1 scope, honest seam): items are ordered **pinned-first, then
newest-first**, where "newest" is a strictly-increasing per-namespace ``seq`` — not
the wall clock, whose coarse resolution on some platforms would tie rapid writes and
make ordering non-deterministic. Search here is a deterministic case-insensitive
**substring** match over content; store-native **semantic** search (``store.search``
with a ``query``) needs the ``Store`` configured with a pgvector embedding index,
which is a sticky-dimension setup decision (§9.5 / §20 note 6) wired in a later
slice. The list/filter/paginate surface stays stable when that lands.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from langgraph.store.base import BaseStore, Item
from pydantic import BaseModel, ConfigDict

from app.memory.namespaces import agent_memory_items_namespace

MemoryKind = Literal["fact", "experience", "session_learning", "summary"]
"""The Explorer's memory sections (FRONTEND_SPEC §14), mapped to §25.2 info types:
``fact`` = semantic, ``experience`` = episodic, ``session_learning`` / ``summary`` =
consolidated learnings written by the post-run consolidation step."""

_PAGE = 100  # page size when sweeping a namespace's records out of the store


class MemoryItem(BaseModel):
    """One structured long-term memory record (ARCH §14 / §25.2)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    kind: MemoryKind
    content: str
    pinned: bool = False
    created_at: datetime
    run_id: UUID | None = None
    seq: int = 0  # strictly-increasing creation order within the namespace; drives ordering


class MemoryItemStore:
    """List / search / write / delete / pin an agent's memory records (§14).

    Args:
        store: the LangGraph ``Store`` (``PostgresStore`` in prod, ``InMemoryStore``
            in tests) — the same store the agent factory mounts, so records written
            by the consolidation step are the records the Explorer reads.
    """

    def __init__(self, store: BaseStore) -> None:
        self._store = store

    # ── reads ────────────────────────────────────────────────────────────────
    def get_item(
        self, *, org_id: UUID, team_id: UUID, agent_id: UUID, item_id: UUID
    ) -> MemoryItem | None:
        """Return one record, or ``None`` if it does not exist (not an error)."""
        namespace = agent_memory_items_namespace(org_id, team_id, agent_id)
        item = self._store.get(namespace, str(item_id))
        return _to_item(item) if item is not None else None

    def list_items(
        self,
        *,
        org_id: UUID,
        team_id: UUID,
        agent_id: UUID,
        kind: MemoryKind | None = None,
        pinned: bool | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryItem]:
        """Return the agent's records, pinned-first then newest, filtered & paginated.

        Filters (all optional, ANDed): ``kind``, ``pinned``, and a case-insensitive
        substring ``query`` over content. Ordering is applied before pagination so
        ``limit``/``offset`` page a stable sequence.
        """
        ordered = self._filtered(
            org_id=org_id, team_id=team_id, agent_id=agent_id, kind=kind, pinned=pinned, query=query
        )
        return ordered[offset : offset + limit]

    def list_page(
        self,
        *,
        org_id: UUID,
        team_id: UUID,
        agent_id: UUID,
        kind: MemoryKind | None = None,
        pinned: bool | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryItem], int]:
        """Like :meth:`list_items` but also returns the **total** match count.

        The total is the count after filtering and *before* paging, so the §14 API
        can render "showing N of total" + page controls ({items, total, limit,
        offset}). One sweep serves both the page and the count.
        """
        ordered = self._filtered(
            org_id=org_id, team_id=team_id, agent_id=agent_id, kind=kind, pinned=pinned, query=query
        )
        return ordered[offset : offset + limit], len(ordered)

    def _filtered(
        self,
        *,
        org_id: UUID,
        team_id: UUID,
        agent_id: UUID,
        kind: MemoryKind | None,
        pinned: bool | None,
        query: str | None,
    ) -> list[MemoryItem]:
        """Sweep + filter + order an agent's records (shared by list/list_page)."""
        items = [_to_item(i) for i in self._sweep(org_id, team_id, agent_id)]
        if kind is not None:
            items = [i for i in items if i.kind == kind]
        if pinned is not None:
            items = [i for i in items if i.pinned is pinned]
        if query:
            needle = query.casefold()
            items = [i for i in items if needle in i.content.casefold()]
        items.sort(key=lambda i: i.seq, reverse=True)
        items.sort(key=lambda i: not i.pinned)  # stable: pinned (False<True) float to top
        return items

    # ── writes ───────────────────────────────────────────────────────────────
    def write_item(
        self,
        *,
        org_id: UUID,
        team_id: UUID,
        agent_id: UUID,
        kind: MemoryKind,
        content: str,
        run_id: UUID | None = None,
    ) -> MemoryItem:
        """Persist a new memory record and return it (the consolidation write path)."""
        namespace = agent_memory_items_namespace(org_id, team_id, agent_id)
        item = MemoryItem(
            id=uuid4(),
            kind=kind,
            content=content,
            pinned=False,
            created_at=datetime.now(UTC),
            run_id=run_id,
            seq=self._next_seq(namespace),
        )
        # index=False: these records are retrieved by namespace + in-service filtering,
        # not vector search yet (see module docstring); avoid requiring a store index.
        self._store.put(namespace, str(item.id), _to_value(item), index=False)
        return item

    def set_pinned(
        self, *, org_id: UUID, team_id: UUID, agent_id: UUID, item_id: UUID, pinned: bool
    ) -> MemoryItem:
        """Pin or unpin a record, preserving its id / content / kind / timestamp.

        Raises:
            KeyError: no record with ``item_id`` exists for this agent.
        """
        namespace = agent_memory_items_namespace(org_id, team_id, agent_id)
        existing = self._store.get(namespace, str(item_id))
        if existing is None:
            raise KeyError(f"memory record {item_id!r} not found for agent {agent_id!r}")
        updated = _to_item(existing).model_copy(update={"pinned": pinned})
        self._store.put(namespace, str(item_id), _to_value(updated), index=False)
        return updated

    def delete_item(self, *, org_id: UUID, team_id: UUID, agent_id: UUID, item_id: UUID) -> bool:
        """Delete a record. Returns ``True`` if one existed, ``False`` if not (idempotent)."""
        namespace = agent_memory_items_namespace(org_id, team_id, agent_id)
        if self._store.get(namespace, str(item_id)) is None:
            return False
        self._store.delete(namespace, str(item_id))
        return True

    # ── internals ────────────────────────────────────────────────────────────
    def _sweep(self, org_id: UUID, team_id: UUID, agent_id: UUID) -> list[Item]:
        """Page every record out of the agent's namespace (small per-agent volume)."""
        namespace = agent_memory_items_namespace(org_id, team_id, agent_id)
        found: list[Item] = []
        offset = 0
        while True:
            page = self._store.search(namespace, limit=_PAGE, offset=offset)
            if not page:
                break
            found.extend(page)
            if len(page) < _PAGE:
                break
            offset += _PAGE
        return found

    def _next_seq(self, namespace: tuple[str, ...]) -> int:
        """Next strictly-increasing creation order for the namespace (max + 1).

        Read-before-write so ordering is correct regardless of clock resolution.
        Per-agent consolidation writes are sequential, so the read stays cheap and
        is not a contention point in practice.
        """
        existing = self._store.search(namespace, limit=_PAGE, offset=0)
        return _max_seq(existing) + 1


def _max_seq(items: Iterable[Item]) -> int:
    return max((int(i.value.get("seq", 0)) for i in items), default=0)


def _to_value(item: MemoryItem) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "content": item.content,
        "pinned": item.pinned,
        "created_at": item.created_at.isoformat(),
        "run_id": str(item.run_id) if item.run_id is not None else None,
        "seq": item.seq,
    }


def _to_item(store_item: Item) -> MemoryItem:
    value = store_item.value
    run_id = value.get("run_id")
    return MemoryItem(
        id=UUID(str(store_item.key)),
        kind=value["kind"],
        content=value["content"],
        pinned=bool(value.get("pinned", False)),
        created_at=datetime.fromisoformat(value["created_at"]),
        run_id=UUID(run_id) if run_id else None,
        seq=int(value.get("seq", 0)),
    )
