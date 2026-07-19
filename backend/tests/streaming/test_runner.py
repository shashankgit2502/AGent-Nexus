"""Integration tests for the graph → AG-UI event driver (ARCH §21.4 / §24).

This is the Step-8 acceptance gate: *a run streams the full typed event sequence*,
and *a HITL pause then resume keeps one monotonic ``seq`` space* (which is what
makes reconnect-replay correct, ARCH §24.8). Runs against ``build_collab_graph``
with an ``InMemorySaver`` and the deterministic stub mesh (no model / agent stack),
exactly like ``tests/graph/test_build.py``.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graph.build import build_collab_graph
from app.graph.state import initial_collab_state
from app.streaming.emitter import RunEventEmitter
from app.streaming.publisher import InProcessEventPublisher
from app.streaming.runner import stream_run
from app.streaming.store import InMemoryRunEventStore


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def test_full_run_streams_the_typed_event_sequence() -> None:
    graph = build_collab_graph(InMemorySaver())
    store = InMemoryRunEventStore()
    emitter = await RunEventEmitter.for_run(
        session_id="sess", run_id="run", store=store, publisher=InProcessEventPublisher()
    )
    state = initial_collab_state(goal="design the API", active_agent_ids=["a", "b"])

    result = await stream_run(graph, graph_input=state, config=_cfg("t-full"), emitter=emitter)

    events = await store.replay("run")
    types = [e["type"] for e in events]

    # The lifecycle the graph nodes emit (ARCH §21.4): open, the parallel
    # contributions across a two-round stub debate, consensus, the auto HITL
    # resolution (lightweight path), the synthesis and the terminal event.
    assert types[0] == "run_start"
    assert types.count("contribution") == 4  # 2 agents × 2 rounds (Bug 4 stub debate)
    # Round 2 emits the inter-agent events that drive the mesh viz (Bug 4, §9.4/§9.10).
    assert "critique" in types
    assert "reasoning" in types
    assert "consensus_update" in types
    assert "hitl_resolved" in types
    assert "synthesis" in types
    assert types[-1] == "run_finished"

    # seq is strictly monotonic from 1, and every envelope is fully formed (§24.3).
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["session_id"] == "sess" and e["run_id"] == "run" and e["ts"] for e in events)

    assert result["interrupted"] is False


async def test_hitl_run_pauses_with_request_then_resumes_keeping_seq() -> None:
    graph = build_collab_graph(InMemorySaver())
    store = InMemoryRunEventStore()
    publisher = InProcessEventPublisher()
    config = _cfg("t-hitl")
    state = initial_collab_state(
        goal="needs review", active_agent_ids=["a", "b"], hitl_enabled=True
    )

    # 1) Initial run pauses at the human gate → terminal event is hitl_request.
    emitter = await RunEventEmitter.for_run(
        session_id="sess", run_id="run", store=store, publisher=publisher
    )
    paused = await stream_run(graph, graph_input=state, config=config, emitter=emitter)

    assert paused["interrupted"] is True
    pre_types = [e["type"] for e in await store.replay("run")]
    assert pre_types[0] == "run_start"
    assert pre_types[-1] == "hitl_request"
    assert "run_finished" not in pre_types

    # 2) Resume with a human decision → run finishes; a fresh emitter continues seq.
    resumed_emitter = await RunEventEmitter.for_run(
        session_id="sess", run_id="run", store=store, publisher=publisher
    )
    done = await stream_run(
        graph, graph_input=Command(resume="approve"), config=config, emitter=resumed_emitter
    )

    assert done["interrupted"] is False
    all_events = await store.replay("run")
    all_types = [e["type"] for e in all_events]
    assert "hitl_resolved" in all_types
    assert all_types[-1] == "run_finished"

    # One contiguous, monotonic seq space across the pause/resume boundary (§24.3/§24.8).
    assert [e["seq"] for e in all_events] == list(range(1, len(all_events) + 1))
