"""Teams router (ARCH §14 — Teams & workspace). Thin: logic via the repository."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import DbSession, Org
from app.db.models import Session as SessionModel
from app.db.models import Team
from app.db.repositories import OrgScopedRepository
from app.schemas.sessions import SessionRead
from app.schemas.teams import TeamCreate, TeamRead, TeamUpdate

router = APIRouter(tags=["teams"])


@router.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, db: DbSession, org: Org) -> Team:
    """Create a team in the active org (ARCH §14)."""
    repo = OrgScopedRepository(db, Team, org.org_id)
    team = Team(
        org_id=org.org_id,
        created_by=org.user_id,
        name=payload.name,
        description=payload.description,
        goal_title=payload.goal_title,
        goal_description=payload.goal_description,
        success_criteria=payload.success_criteria,
        embedding_model_id=payload.embedding_model_id,
    )
    return await repo.add(team)


@router.get("/teams", response_model=list[TeamRead])
async def list_teams(db: DbSession, org: Org) -> list[Team]:
    """List the active org's teams (ARCH §14)."""
    repo = OrgScopedRepository(db, Team, org.org_id)
    return list(await repo.list())


@router.get("/teams/{team_id}", response_model=TeamRead)
async def get_team(team_id: UUID, db: DbSession, org: Org) -> Team:
    """Fetch one team (ARCH §14)."""
    team = await OrgScopedRepository(db, Team, org.org_id).get(team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found")
    return team


@router.put("/teams/{team_id}", response_model=TeamRead)
async def update_team(team_id: UUID, payload: TeamUpdate, db: DbSession, org: Org) -> Team:
    """Patch a team — only fields present in the payload change (ARCH §14)."""
    repo = OrgScopedRepository(db, Team, org.org_id)
    team = await repo.get(team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    await db.flush()
    await db.refresh(team)
    return team


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(team_id: UUID, db: DbSession, org: Org) -> None:
    """Soft-delete a team; its agents/sessions cascade via FK (ARCH §14, TECHNICAL §11.2)."""
    if not await OrgScopedRepository(db, Team, org.org_id).soft_delete(team_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found")


@router.get("/teams/{team_id}/sessions", response_model=list[SessionRead])
async def list_team_sessions(team_id: UUID, db: DbSession, org: Org) -> list[SessionModel]:
    """Session history for a team (ARCH §14)."""
    return list(await OrgScopedRepository(db, SessionModel, org.org_id).list(team_id=team_id))
