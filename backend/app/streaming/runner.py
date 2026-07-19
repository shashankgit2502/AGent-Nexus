"""Graph → AG-UI event driver (ARCH §21.4 run sequence, §24).

This is "event emission from the graph": it runs the compiled collaboration graph
and turns its execution into the ordered AG-UI event stream, pushing every event
through a :class:`~app.streaming.emitter.RunEventEmitter` (seq + persist + fan-out).

How events leave the graph (R1-verified, langgraph 1.2.5)
--------------------------------------------------------
The graph nodes already append AG-UI records to the additive ``events`` channel of
``CollabState`` (``orchestrator`` → ``run_start``, ``agent_turn`` →
``contribution``/``error``, ``consensus`` → ``consensus_update``, ``hitl`` →
``hitl_resolved``, ``synthesizer`` → ``synthesis``, ``end`` → ``run_finished``).
We observe those incrementally with **``astream(stream_mode="updates",
version="v2")``**:

* ``version="v2"`` gives the unified StreamPart shape ``{"type","ns","data"}``
  regardless of mode/subgraphs (verified: ``astream`` accepts ``version=``;
  default is ``v1``). For ``type == "updates"``, ``data`` is ``{node_name: update}``
  — the *delta* each node returned this super-step. Parallel mesh agents
  (``Send()`` fan-out) each surface as their **own** updates chunk, so every
  agent's ``contribution`` event flows out exactly once, in execution order.

HITL pause (the one event not in the update stream)
---------------------------------------------------
The ``hitl`` node calls ``interrupt(payload)`` and therefore never *returns* on the
initial run — so its review payload is not in any node update. In v2, an interrupt
is exposed on ``StateSnapshot.interrupts`` (verified: ``StateSnapshot`` has an
``interrupts`` field; each ``Interrupt`` has ``.value``). After the stream drains,
we read the state and, if a ``hitl_request`` interrupt is pending, emit it. The
``hitl`` node's review payload is already shaped as the AG-UI ``hitl_request`` body
(``app/graph/nodes/hitl._review_payload``), so this is a faithful projection, not a
fabricated event. On *resume* the node returns normally and emits ``hitl_resolved``
through the ordinary update path — no spurious second ``hitl_request``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from app.graph.context import MeshContext
from app.streaming.emitter import RunEventEmitter

logger = logging.getLogger(__name__)

# Marker key for a pending human-review interrupt (ARCH §4.5 / hitl node payload).
_HITL_REQUEST = "hitl_request"


def _hitl_request_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the hitl node's interrupt payload into a raw AG-UI ``hitl_request``.

    The payload is ``{"type": "hitl_request", <candidate, ranking, ...>}``; the
    envelope's ``type`` is the marker and everything else becomes ``data``.
    """
    return {"type": _HITL_REQUEST, "data": {k: v for k, v in payload.items() if k != "type"}}


async def stream_run(
    graph: CompiledStateGraph[Any, Any, Any, Any],
    *,
    graph_input: Any,
    config: RunnableConfig,
    emitter: RunEventEmitter,
    context: MeshContext | None = None,
) -> dict[str, Any]:
    """Drive one graph invocation (or resume) and emit its AG-UI events in order.

    Args:
        graph: a compiled collaboration graph (``build_collab_graph``).
        graph_input: the initial ``CollabState`` for a new run, **or** a
            ``langgraph.types.Command(resume=...)`` to continue a HITL-paused run.
        config: the LangGraph config carrying ``{"configurable": {"thread_id": ...}}``.
        emitter: the run's :class:`RunEventEmitter` (seq + persist + fan-out).
        context: optional :class:`MeshContext` (real ``runner``/``synthesizer``);
            omit for the deterministic stub path (foundation/integration tests).

    Returns:
        A small status dict: ``{"interrupted": bool, "last_seq": int}``. The caller
        (the run-launch route, Step 9) uses ``interrupted`` to decide whether the
        run is paused awaiting a human decision.
    """
    async for chunk in graph.astream(
        graph_input,
        config,
        context=context,
        stream_mode="updates",
        version="v2",
    ):
        # Discriminate the v2 StreamPart union on its literal ``type`` so the
        # static type of ``chunk["data"]`` narrows to the updates mapping.
        if chunk["type"] != "updates":
            continue
        for node_update in chunk["data"].values():
            if not isinstance(node_update, Mapping):
                continue
            for raw in node_update.get("events", []) or []:
                await emitter.emit(raw)

    # Stream drained: the run either finished or paused at the HITL interrupt.
    interrupted = await _emit_pending_hitl_request(graph, config=config, emitter=emitter)
    return {"interrupted": interrupted, "last_seq": emitter.last_seq}


async def _emit_pending_hitl_request(
    graph: CompiledStateGraph[Any, Any, Any, Any],
    *,
    config: RunnableConfig,
    emitter: RunEventEmitter,
) -> bool:
    """Emit ``hitl_request`` if the run paused at the human gate. Returns paused?."""
    snapshot = await graph.aget_state(config)
    pending = False
    for interrupt in snapshot.interrupts:
        value = interrupt.value
        if isinstance(value, Mapping) and value.get("type") == _HITL_REQUEST:
            await emitter.emit(_hitl_request_record(value))
            pending = True
        else:
            # An interrupt we don't recognise should not be silently dropped (R3).
            logger.warning("unrecognised interrupt payload on run; not emitting: %r", value)
    return pending
