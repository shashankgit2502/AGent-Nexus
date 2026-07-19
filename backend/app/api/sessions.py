"""Sessions & collaboration router (ARCH §14 — Collaboration).

Create a session under a team, launch a run (drives the collaboration graph and the
AG-UI stream), and resume a HITL-paused run. The AG-UI event stream itself is the
WebSocket endpoint mounted from ``app.streaming.websocket`` (ARCH §24.2).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status

from app.core.deps import DbSession, Org
from app.db.models import Artifact, Run, Team
from app.db.models import Session as SessionModel
from app.db.repositories import OrgScopedRepository
from app.schemas.sessions import (
    ArtifactRead,
    ResumeRequest,
    RunLaunch,
    RunLaunchResponse,
    RunRead,
    SessionCreate,
    SessionRead,
)
from app.streaming.run_service import launch_run, resume_run

router = APIRouter(tags=["sessions"])


@router.post(
    "/teams/{team_id}/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED
)
async def create_session(
    team_id: UUID, payload: SessionCreate, db: DbSession, org: Org
) -> SessionModel:
    """Start a collaboration session for a team (ARCH §14). Binds a checkpointer thread."""
    if await OrgScopedRepository(db, Team, org.org_id).get(team_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found")
    session = SessionModel(
        org_id=org.org_id,
        team_id=team_id,
        thread_id=payload.thread_id or f"sess-{uuid4()}",
        created_by=org.user_id,
    )
    return await OrgScopedRepository(db, SessionModel, org.org_id).add(session)


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(db: DbSession, org: Org) -> list[SessionModel]:
    """List **all** of the active org's sessions, newest-agnostic (ARCH §14).

    The per-team history view uses ``GET /teams/{id}/sessions``; this org-wide list
    backs the global History screen (FRONTEND_SPEC History).
    """
    return list(await OrgScopedRepository(db, SessionModel, org.org_id).list())


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def get_session(session_id: UUID, db: DbSession, org: Org) -> SessionModel:
    """Fetch one session (ARCH §14)."""
    session = await OrgScopedRepository(db, SessionModel, org.org_id).get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    return session


@router.get("/sessions/{session_id}/runs", response_model=list[RunRead])
async def list_session_runs(session_id: UUID, db: DbSession, org: Org) -> list[Run]:
    """List a session's runs, newest first (ARCH §14).

    Backs the History screen: a session has no run id of its own, so the client
    fetches its runs here, then pulls the terminal run's output via
    ``GET /runs/{id}/artifact``. 404s when the session is not in this org. Ordered
    by ``created_at`` desc (always present, unlike the nullable ``started_at``), so
    the first row is the latest run.
    """
    if await OrgScopedRepository(db, SessionModel, org.org_id).get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    runs = await OrgScopedRepository(db, Run, org.org_id).list(
        session_id=session_id, order_by="created_at", descending=True
    )
    return list(runs)


@router.get("/runs/{run_id}/artifact", response_model=ArtifactRead)
async def get_run_artifact(run_id: UUID, db: DbSession, org: Org) -> Artifact:
    """Return a finished run's persisted output (ARCH §14, §11.4).

    Backs the History/Workspace "final output" panel for a completed run. 404s when
    the run does not exist in this org or has not yet produced an artifact (a run is
    only finalized with an artifact when it completes — a paused/running run has none).
    """
    if await OrgScopedRepository(db, Run, org.org_id).get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="run not found")
    artifacts = await OrgScopedRepository(db, Artifact, org.org_id).list(run_id=run_id)
    if not artifacts:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="artifact not found for this run")
    return artifacts[0]


@router.post("/sessions/{session_id}/run", response_model=RunLaunchResponse)
async def launch_session_run(
    session_id: UUID, payload: RunLaunch, request: Request, db: DbSession, org: Org
) -> RunLaunchResponse:
    """Launch a run on a session and drive the AG-UI stream (ARCH §21.4).

    Returns the run, whether it paused at the human gate, and the WS URL to
    subscribe to the live/replayable event stream (ARCH §24.2/§24.8).
    """
    session = await OrgScopedRepository(db, SessionModel, org.org_id).get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")

    result = await launch_run(app=request.app, db=db, org=org, session=session, payload=payload)
    return RunLaunchResponse(
        run=result.run,
        interrupted=result.interrupted,
        stream_url=f"/sessions/{session_id}/stream?run_id={result.run.id}",
    )


@router.post("/sessions/{session_id}/resume", response_model=RunLaunchResponse)
async def resume_session_run(
    session_id: UUID, payload: ResumeRequest, request: Request, db: DbSession, org: Org
) -> RunLaunchResponse:
    """Resume a HITL-paused run with the human decision (ARCH §4.5)."""
    session_repo = OrgScopedRepository(db, SessionModel, org.org_id)
    session = await session_repo.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    run = await OrgScopedRepository(db, Run, org.org_id).get(payload.run_id)
    if run is None or run.session_id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="run not found for this session")

    result = await resume_run(
        app=request.app, db=db, org=org, session=session, run=run, payload=payload
    )
    return RunLaunchResponse(
        run=result.run,
        interrupted=result.interrupted,
        stream_url=f"/sessions/{session_id}/stream?run_id={result.run.id}",
    )
