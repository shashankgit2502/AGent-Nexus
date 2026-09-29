"""Step-9 acceptance: create a team + agents + session and launch a run via the API.

This is the BUILD_PLAYBOOK Step-9 "Done when" check, exercised end-to-end against
the **real** app and a **real** Postgres (the migration must be applied first via
``alembic upgrade head``). It drives the FastAPI app with ``TestClient`` (which runs
the lifespan: LangGraph checkpointer/store setup + default-org seeding), so it covers:

* the org-context dependency + RLS GUC (every write is org-scoped),
* the CRUD routers (teams/agents/sessions),
* the run-launch route driving the collaboration graph (stub path — no provider
  keys needed) through to a persisted artifact, and
* the AG-UI event stream persisted to ``run_events`` and replayable over the WS.

Requires the DB to be up and migrated; marked ``integration`` so it can be excluded
in environments without Postgres.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


def _wait_for(fn: Callable[[], Any], *, attempts: int = 100, delay: float = 0.05) -> Any:
    """Poll ``fn`` until it returns truthy (runs complete asynchronously now, §24.5)."""
    for _ in range(attempts):
        result = fn()
        if result:
            return result
        time.sleep(delay)
    raise AssertionError("condition not met within timeout")


def test_create_team_agents_session_and_launch_run() -> None:
    with TestClient(app) as client:
        # Unique team name so the partial-unique index (per org) allows re-runs.
        team_name = f"Acceptance Team {uuid4().hex[:8]}"

        # 1) Create a team.
        r = client.post(
            "/teams",
            json={"name": team_name, "description": "e2e", "success_criteria": ["a clear answer"]},
        )
        assert r.status_code == 201, r.text
        team_id = r.json()["id"]

        # 2) Add two peer agents.
        for name in ("Researcher", "Critic"):
            ra = client.post(
                f"/teams/{team_id}/agents",
                json={"name": name, "instructions": f"You are the {name}."},
            )
            assert ra.status_code == 201, ra.text
        agents = client.get(f"/teams/{team_id}/agents").json()
        assert len(agents) == 2

        # 3) Start a session.
        rs = client.post(f"/teams/{team_id}/sessions", json={})
        assert rs.status_code == 201, rs.text
        session_id = rs.json()["id"]

        # 4) Launch a lightweight run (1 round, HITL off). The run now executes in
        # the background (ARCH §24.5): the POST returns immediately with status
        # "running"; the client watches the live stream over the WS.
        rr = client.post(
            f"/sessions/{session_id}/run",
            json={"query": "What is 2 + 2?", "deep_collaborate": False},
        )
        assert rr.status_code == 200, rr.text
        body = rr.json()
        assert body["interrupted"] is False
        assert body["run"]["status"] == "running"
        run_id = body["run"]["id"]
        assert f"run_id={run_id}" in body["stream_url"]

        # 5) The AG-UI stream is delivered live (and replayable) over the WS.
        types: list[str] = []
        with client.websocket_connect(f"/sessions/{session_id}/stream?run_id={run_id}") as ws:
            while True:
                event = ws.receive_json()
                assert event["run_id"] == run_id
                types.append(event["type"])
                if event["type"] == "run_finished":
                    break
        # The run produced an ordered lifecycle ending in run_finished, now with the
        # round/turn boundary markers the frontend Session Workspace needs (§24.4).
        assert types[0] == "run_start"
        assert "round_start" in types
        assert "agent_turn_start" in types
        assert "run_finished" in types

        # 6) Slice-0 read endpoints (ARCH §14). The artifact is persisted just after
        # run_finished by the background task, so poll for it (completion is async).
        got = _wait_for(
            lambda: (r := client.get(f"/runs/{run_id}/artifact")).status_code == 200 and r
        )
        assert got.json()["kind"] == "synthesis"
        assert got.json()["run_id"] == run_id

        sessions = client.get("/sessions").json()
        assert any(s["id"] == session_id for s in sessions)

        stats = client.get("/stats").json()
        assert stats["teams"] >= 1
        assert stats["agents"] >= 2
        assert stats["completed_runs"] >= 1


def test_list_session_runs_backs_history_artifact_view() -> None:
    """`GET /sessions/{id}/runs` lists a session's runs so History can fetch the
    terminal run's artifact (the session itself carries no run id)."""
    with TestClient(app) as client:
        team_id = client.post("/teams", json={"name": f"Runs {uuid4().hex[:8]}"}).json()["id"]
        client.post(f"/teams/{team_id}/agents", json={"name": "Solo"})
        session_id = client.post(f"/teams/{team_id}/sessions", json={}).json()["id"]

        # The run row is created+committed at launch (before backgrounding), so it is
        # listable immediately — no need to wait for the run to finish.
        run_id = client.post(
            f"/sessions/{session_id}/run",
            json={"query": "What is 2 + 2?", "deep_collaborate": False},
        ).json()["run"]["id"]

        listed = client.get(f"/sessions/{session_id}/runs")
        assert listed.status_code == 200, listed.text
        runs = listed.json()
        assert any(r["id"] == run_id for r in runs)
        # The listed run belongs to this session and exposes the History fields.
        run = next(r for r in runs if r["id"] == run_id)
        assert run["session_id"] == session_id
        assert run["conversation_id"] is None
        assert set(run) >= {"status", "rounds", "converged", "query"}

        # The terminal run's artifact is then reachable (poll — completion is async).
        got = _wait_for(
            lambda: (a := client.get(f"/runs/{run_id}/artifact")).status_code == 200 and a
        )
        assert got.json()["run_id"] == run_id

        # Unknown session → 404 (org-scoped, like the sibling reads).
        assert client.get(f"/sessions/{uuid4()}/runs").status_code == 404


def test_deep_run_pauses_at_hitl_then_resumes() -> None:
    with TestClient(app) as client:
        team_name = f"HITL Team {uuid4().hex[:8]}"
        team_id = client.post("/teams", json={"name": team_name}).json()["id"]
        client.post(f"/teams/{team_id}/agents", json={"name": "Solo"})
        session_id = client.post(f"/teams/{team_id}/sessions", json={}).json()["id"]

        # Deep run: full graph with the human gate. Executes in the background and
        # pauses at HITL — the client observes the pause via the live hitl_request
        # event (not the launch response, which returns immediately, ARCH §24.5).
        launched = client.post(
            f"/sessions/{session_id}/run",
            json={"query": "Plan a launch.", "deep_collaborate": True, "max_rounds": 1},
        ).json()
        assert launched["interrupted"] is False
        assert launched["run"]["status"] == "running"
        run_id = launched["run"]["id"]

        with client.websocket_connect(f"/sessions/{session_id}/stream?run_id={run_id}") as ws:
            # Drain to the pause signal.
            while ws.receive_json()["type"] != "hitl_request":
                pass
            # Resume with approve → the run continues (a fresh background task) and
            # streams the rest over the SAME subscription, ending in run_finished.
            resumed = client.post(
                f"/sessions/{session_id}/resume",
                json={"run_id": run_id, "decision": "approve"},
            )
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["run"]["status"] == "running"
            while ws.receive_json()["type"] != "run_finished":
                pass

        # The approved run finalises a synthesis artifact (async; poll for it).
        got = _wait_for(
            lambda: (r := client.get(f"/runs/{run_id}/artifact")).status_code == 200 and r
        )
        assert got.json()["kind"] == "synthesis"


def test_org_isolation_hides_other_orgs_team() -> None:
    """A team created in the default org is invisible to a different org (RLS, §11.7)."""
    with TestClient(app) as client:
        team_id = client.post("/teams", json={"name": f"Iso {uuid4().hex[:8]}"}).json()["id"]
        # Same team, default org → visible.
        assert client.get(f"/teams/{team_id}").status_code == 200
        # A different (random) org → not found (RLS + org filter both exclude it).
        other = client.get(f"/teams/{team_id}", headers={"X-Org-Id": str(uuid4())})
        assert other.status_code == 404


def test_team_update_and_delete() -> None:
    """PUT patches only the supplied fields; DELETE soft-removes the team (ARCH §14)."""
    with TestClient(app) as client:
        team = client.post(
            "/teams", json={"name": f"Edit {uuid4().hex[:8]}", "goal_title": "old"}
        ).json()
        team_id = team["id"]

        # Partial update: name unchanged, goal_title replaced.
        updated = client.put(f"/teams/{team_id}", json={"goal_title": "new goal"})
        assert updated.status_code == 200
        body = updated.json()
        assert body["goal_title"] == "new goal"
        assert body["name"] == team["name"]

        # Delete → 204, then the team is gone from reads and the list.
        assert client.delete(f"/teams/{team_id}").status_code == 204
        assert client.get(f"/teams/{team_id}").status_code == 404
        assert all(t["id"] != team_id for t in client.get("/teams").json())

        # Deleting again is a clean 404 (idempotent soft-delete).
        assert client.delete(f"/teams/{team_id}").status_code == 404


def test_conversation_delete_removes_it_from_history() -> None:
    """DELETE soft-removes a conversation and drops it from the list (ARCH §8.5)."""
    with TestClient(app) as client:
        team_id = client.post("/teams", json={"name": f"Conv {uuid4().hex[:8]}"}).json()["id"]
        conv_id = client.post("/conversations", json={"team_id": team_id}).json()["id"]

        assert any(c["id"] == conv_id for c in client.get("/conversations").json())
        assert client.delete(f"/conversations/{conv_id}").status_code == 204
        assert client.get(f"/conversations/{conv_id}").status_code == 404
        assert all(c["id"] != conv_id for c in client.get("/conversations").json())
        assert client.delete(f"/conversations/{conv_id}").status_code == 404
