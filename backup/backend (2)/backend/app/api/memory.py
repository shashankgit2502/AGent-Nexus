"""Memory Explorer router (ARCH §14/§10/§25.1, FRONTEND_SPEC §14).

Two surfaces over an agent's long-term memory, both org-scoped (§25.1 org-prefixed
namespaces) and both reusing the real ``Store`` primitive (R2 — no re-implemented
store access). The store client is synchronous, so every store touch runs off the
event loop via ``run_in_threadpool``.

* **Recall view** — ``GET /agents/{id}/memory`` returns the rendered private recall
  file (``/memories/AGENTS.md``) plus the read-only team-shared layer
  (:class:`~app.memory.service.MemoryService`).
* **Records CRUD** (§14) — list / search / delete / pin the structured per-item
  memories (:class:`~app.memory.items.MemoryItemStore`): the Memory Explorer's
  source of truth, written by the post-run consolidation step (ARCH §25.3).

Agent resolution is a single dependency (:func:`get_scoped_agent`) so every route
shares the org-scoped lookup + 404, and tests can override it to exercise the routes
without a database. Search is a deterministic case-insensitive substring match for
now; store-native **semantic** search (``Store.search(query=…)``) needs the
``PostgresStore`` configured with a pgvector embedding index — a sticky-dimension
setup decision (§9.5 / §20 note 6) — so the ``q`` parameter contract is stable and
upgrades in place.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.core.deps import DbSession, Org
from app.db.models import Agent
from app.db.repositories import OrgScopedRepository
from app.memory.items import MemoryItemStore, MemoryKind
from app.memory.service import MemoryService
from app.schemas.memory import MemoryItemRead, MemoryPage, MemoryPinUpdate

router = APIRouter(tags=["memory"])


class AgentMemoryRead(BaseModel):
    """An agent's long-term memory snapshot (private recall file + shared layer)."""

    agent_id: UUID
    team_id: UUID
    private: str | None
    shared: str | None


async def get_scoped_agent(agent_id: UUID, db: DbSession, org: Org) -> Agent:
    """Resolve an org-scoped agent or raise 404 (shared authz + existence boundary).

    A dependency (not an inline helper) so every memory route enforces the same
    org-scoping and so tests can override it to drive the routes without a database.
    """
    agent = await OrgScopedRepository(db, Agent, org.org_id).get(agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agent not found")
    return agent


ScopedAgent = Annotated[Agent, Depends(get_scoped_agent)]


def _item_store(request: Request) -> MemoryItemStore:
    return MemoryItemStore(request.app.state.memory_store)


@router.get("/agents/{agent_id}/memory", response_model=AgentMemoryRead)
async def get_agent_memory(request: Request, org: Org, agent: ScopedAgent) -> AgentMemoryRead:
    """Return an agent's rendered private recall file and the team-shared layer (§25.1)."""
    service = MemoryService(request.app.state.memory_store)
    private = await run_in_threadpool(
        service.read, org_id=org.org_id, team_id=agent.team_id, agent_id=agent.id
    )
    shared = await run_in_threadpool(
        service.read_shared, org_id=org.org_id, team_id=agent.team_id
    )
    return AgentMemoryRead(agent_id=agent.id, team_id=agent.team_id, private=private, shared=shared)


@router.get("/agents/{agent_id}/memories", response_model=MemoryPage)
async def list_agent_memories(
    request: Request,
    org: Org,
    agent: ScopedAgent,
    kind: MemoryKind | None = None,
    q: str | None = None,
    pinned: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MemoryPage:
    """List an agent's structured memory records — filtered, searched, paginated (§14)."""
    items, total = await run_in_threadpool(
        _item_store(request).list_page,
        org_id=org.org_id,
        team_id=agent.team_id,
        agent_id=agent.id,
        kind=kind,
        pinned=pinned,
        query=q,
        limit=limit,
        offset=offset,
    )
    return MemoryPage(
        items=[MemoryItemRead.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/agents/{agent_id}/memories/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_memory(
    item_id: UUID, request: Request, org: Org, agent: ScopedAgent
) -> Response:
    """Delete one memory record (404 if it never existed)."""
    deleted = await run_in_threadpool(
        _item_store(request).delete_item,
        org_id=org.org_id,
        team_id=agent.team_id,
        agent_id=agent.id,
        item_id=item_id,
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="memory record not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/agents/{agent_id}/memories/{item_id}", response_model=MemoryItemRead)
async def pin_agent_memory(
    item_id: UUID, body: MemoryPinUpdate, request: Request, org: Org, agent: ScopedAgent
) -> MemoryItemRead:
    """Pin or unpin a memory record (§14); returns the updated record."""
    try:
        item = await run_in_threadpool(
            _item_store(request).set_pinned,
            org_id=org.org_id,
            team_id=agent.team_id,
            agent_id=agent.id,
            item_id=item_id,
            pinned=body.pinned,
        )
    except KeyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="memory record not found"
        ) from exc
    return MemoryItemRead.model_validate(item)
