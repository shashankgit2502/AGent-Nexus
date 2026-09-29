"""Agents router (ARCH §14/§22). Create under a team; update/delete by id."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.agents.model_gate import AgentModelNotToolCapable, assert_agent_model_tool_capable
from app.core.deps import DbSession, Org
from app.db.models import Agent, Team
from app.db.repositories import OrgScopedRepository
from app.schemas.agents import AgentCreate, AgentRead, AgentUpdate

router = APIRouter(tags=["agents"])


@router.post(
    "/teams/{team_id}/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED
)
async def create_agent(team_id: UUID, payload: AgentCreate, db: DbSession, org: Org) -> Agent:
    """Add a peer agent config to a team (ARCH §22.1).

    The team must exist in this org. The ``supports_tools`` hard gate (ARCH §9.3) is
    enforced **here, at config time** (as well as at runtime): assigning a non-tool model
    is rejected up-front so a misconfiguration is caught in the Agent Builder rather than
    surfacing later as a silently-abstaining agent. ``supports_tools`` is a static catalog
    fact, so this does not require the provider connection to be validated first.
    """
    if await OrgScopedRepository(db, Team, org.org_id).get(team_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found")
    try:
        await assert_agent_model_tool_capable(
            db,
            org_id=org.org_id,
            profile_id=payload.profile_id,
            override_model_id=payload.override_model_id,
        )
    except AgentModelNotToolCapable as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    repo = OrgScopedRepository(db, Agent, org.org_id)
    agent = Agent(
        org_id=org.org_id,
        team_id=team_id,
        created_by=org.user_id,
        name=payload.name,
        description=payload.description,
        instructions=payload.instructions,
        capabilities=payload.capabilities,
        memory_enabled=payload.memory_enabled,
        profile_id=payload.profile_id,
        override_model_id=payload.override_model_id,
        embedding_model_id=payload.embedding_model_id,
    )
    return await repo.add(agent)


@router.get("/teams/{team_id}/agents", response_model=list[AgentRead])
async def list_team_agents(team_id: UUID, db: DbSession, org: Org) -> list[Agent]:
    """List a team's agents (ARCH §14)."""
    return list(await OrgScopedRepository(db, Agent, org.org_id).list(team_id=team_id))


@router.get("/agents/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: UUID, db: DbSession, org: Org) -> Agent:
    """Fetch one agent config."""
    agent = await OrgScopedRepository(db, Agent, org.org_id).get(agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agent not found")
    return agent


@router.put("/agents/{agent_id}", response_model=AgentRead)
async def update_agent(agent_id: UUID, payload: AgentUpdate, db: DbSession, org: Org) -> Agent:
    """Patch an agent config — only fields present in the payload change (ARCH §14)."""
    repo = OrgScopedRepository(db, Agent, org.org_id)
    agent = await repo.get(agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agent not found")
    fields = payload.model_dump(exclude_unset=True)
    # Gate the §9.3 capability on the MERGED selection (existing values overridden by the
    # patch), before mutating — e.g. a PUT that only changes `override_model_id` must be
    # checked against the new override + the agent's current profile.
    try:
        await assert_agent_model_tool_capable(
            db,
            org_id=org.org_id,
            profile_id=fields.get("profile_id", agent.profile_id),
            override_model_id=fields.get("override_model_id", agent.override_model_id),
        )
    except AgentModelNotToolCapable as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    for field, value in fields.items():
        setattr(agent, field, value)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: UUID, db: DbSession, org: Org) -> None:
    """Soft-delete an agent (ARCH §14)."""
    if not await OrgScopedRepository(db, Agent, org.org_id).soft_delete(agent_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="agent not found")
