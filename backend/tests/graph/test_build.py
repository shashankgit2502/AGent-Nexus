"""Integration tests for ``build_collab_graph`` (ARCHITECTURE.md §7).

Covers the Step-2 acceptance gate (TECHNICAL.md §10):
  * the graph compiles and runs end-to-end with a stub agent node,
  * the consensus loop terminates by convergence AND by ``max_rounds``,
  * a trivial run checkpoints and RESUMES on the same ``thread_id`` with a real
    ``PostgresSaver`` — proven across a HITL ``interrupt()`` and across a fresh
    graph instance (simulating a process restart).
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from app.core.config import get_settings
from app.graph.build import build_collab_graph
from app.graph.state import initial_collab_state


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


# ── In-memory: graph behaviour (fast, no DB) ─────────────────────────────────


def test_default_run_debates_a_second_round_then_converges() -> None:
    """The stub mesh debates a second round, then converges (Bug 4).

    Round 1 sits below τ (0.6 < 0.85) so the loop runs a second round where peers can
    build on / critique each other — round 2 is confident (0.9) and converges. This is
    what makes the keys-free demo produce reply + critique edges (§9.10) and a real
    debate thread (§9.4) instead of a single static round.
    """
    app = build_collab_graph(InMemorySaver())
    state = initial_collab_state(goal="design the API", active_agent_ids=["a", "b"])

    out = app.invoke(state, _cfg("converge"))

    assert out["status"] == "done"
    assert out["converged"] is True  # round-2 stub confidence 0.9 ≥ τ 0.85
    assert {c["round"] for c in out["contributions"]} == {1, 2}
    assert len(out["contributions"]) == 4  # 2 agents × 2 rounds
    assert out["final_output"].startswith("[stub]")
    emitted = [e["type"] for e in out["events"]]
    assert emitted[0] == "run_start"
    assert "consensus_update" in emitted
    assert emitted[-1] == "run_finished"


def test_stub_mesh_emits_inter_agent_edge_events_in_round_two() -> None:
    """Bug 4 regression: the round-2 stub emits the events that drive the mesh viz.

    A `critique` event (sender→target) and a `contribution` carrying `responds_to`
    are exactly what `buildGraphModel` turns into animated critique + reply edges,
    and what `buildDebateTimeline` renders. Round 1 emits neither (no peers yet).
    """
    app = build_collab_graph(InMemorySaver())
    state = initial_collab_state(goal="g", active_agent_ids=["a", "b"])

    out = app.invoke(state, _cfg("edges"))

    critiques = [e for e in out["events"] if e["type"] == "critique"]
    assert critiques, "round-2 stub must emit at least one critique event (critique edge)"
    assert all(e["data"]["round"] == 2 for e in critiques)  # never on the opening round
    assert all({"sender", "target", "severity"} <= e["data"].keys() for e in critiques)

    round_two_contribs = [
        e
        for e in out["events"]
        if e["type"] == "contribution" and e["data"]["round"] == 2
    ]
    assert any(e["data"].get("responds_to") for e in round_two_contribs), (
        "round-2 contributions must carry responds_to (reply edges)"
    )
    # Opening round stays edge-free (faithful to §23.4 — no peers visible yet).
    assert not [
        e for e in out["events"] if e["type"] == "contribution" and e["data"]["round"] == 1
        if e["data"].get("responds_to")
    ]


def test_run_loops_until_max_rounds_when_never_converging() -> None:
    app = build_collab_graph(InMemorySaver())
    # τ unreachable → termination is driven purely by max_rounds.
    state = initial_collab_state(
        goal="hard problem",
        active_agent_ids=["a", "b"],
        confidence_threshold=2.0,
        max_rounds=3,
    )

    out = app.invoke(state, _cfg("maxrounds"))

    assert out["status"] == "done"
    assert out["converged"] is False
    # Bug 4: max_rounds=N runs exactly N debate rounds (locked §3 "loop until rounds ≥ N").
    rounds_seen = {c["round"] for c in out["contributions"]}
    assert rounds_seen == {1, 2, 3}
    assert len(out["contributions"]) == 6  # 2 agents × 3 rounds


# ── Postgres: the real checkpoint/resume acceptance gate ─────────────────────


def _postgres_available(url: str) -> bool:
    try:
        with psycopg.connect(url, connect_timeout=3):
            return True
    except (psycopg.OperationalError, psycopg.Error):
        return False


_PG_URL = get_settings().LANGGRAPH_PG_URL
requires_postgres = pytest.mark.skipif(
    not _postgres_available(_PG_URL),
    reason="LangGraph Postgres (docker compose up) not reachable",
)


@requires_postgres
def test_postgres_checkpoint_and_resume_across_instances() -> None:
    """Pause on HITL with one PostgresSaver, resume with a *fresh* one.

    This is the strongest form of the acceptance check: the resuming graph is a
    brand-new instance with its own DB connection, so the only way it can
    continue is by reading the persisted checkpoint for the thread.
    """
    thread_id = f"resume-{uuid.uuid4()}"
    initial = initial_collab_state(
        goal="persisted goal",
        active_agent_ids=["a", "b"],
        hitl_enabled=True,  # force the interrupt() pause
    )

    # Instance A: run until the HITL interrupt, then drop the connection.
    with PostgresSaver.from_conn_string(_PG_URL) as saver_a:
        saver_a.setup()  # idempotent CREATE TABLE IF NOT EXISTS
        app_a = build_collab_graph(saver_a)
        result = app_a.invoke(initial, _cfg(thread_id))
        assert "__interrupt__" in result  # paused, not finished
        assert app_a.get_state(_cfg(thread_id)).next == ("hitl",)

    # Instance B: a separate connection + freshly built graph resumes the thread.
    with PostgresSaver.from_conn_string(_PG_URL) as saver_b:
        app_b = build_collab_graph(saver_b)
        # The pending state is visible purely from the persisted checkpoint.
        assert app_b.get_state(_cfg(thread_id)).next == ("hitl",)

        final = app_b.invoke(Command(resume="approve"), _cfg(thread_id))
        assert final["status"] == "done"
        assert final["converged"] is True
        decisions = [e["data"]["decision"] for e in final["events"] if e["type"] == "hitl_resolved"]
        assert decisions == ["approve"]
